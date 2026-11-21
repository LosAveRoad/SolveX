import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { SubmitTool } from "../ports/AgentRunner.js";
import { changedFiles, fingerprint, type Fingerprint } from "./fileGuard.js";
import { findPlaceholder, memoRequired, paperGaps } from "./paperGate.js";

/**
 * 提交工具（ADR-0015）。r6 里「做完了」靠最后一条回复文字判断：空回复、说完就停、占位符摘要都被当成交付。
 * 现在每个阶段以一次被接受的提交结束；check 是确定性的检查，不合格就把缺什么原样回给模型，
 * 模型在同一轮里补齐后再提交。
 */

/** 去掉结论行后，评审正文少于这个字数就不接受（r6：GLM 有时以空回复或只有结论行结束评审）。 */
export const MIN_REVIEW_CHARS = 400;
/** 备忘录正文下限（约半页）。 */
export const MIN_MEMO_CHARS = 1200;
export const MIN_FIX_SUMMARY_CHARS = 40;

const VERDICT_LINE = /VERIFICATION_RESULT:\s*(SATISFIED|NEEDS_REVISION)/gi;
const str = (v: unknown): string => (typeof v === "string" ? v : "");

export const submitNudge = (tool: string, missing: string[] = []): string =>
  `[SolveX] You ended your turn without a successful call to \`${tool}\`. The task only counts as finished when ` +
  `\`${tool}\` accepts your submission; your reply text is not used.` +
  (missing.length ? `\nStill missing:\n${missing.map((x) => `- ${x}`).join("\n")}` : "") +
  "\nContinue from where you stopped — do not start over. Finish the remaining work, then call " +
  `\`${tool}\`. If it rejected an earlier submission, fix what it listed and call it again.`;

/** 追加在任务末尾的收尾说明。 */
export const submitInstruction = (tool: string, what: string): string =>
  `\n\nFINISHING (SolveX): when ${what}, call the \`${tool}\` tool. That call is the only way to finish this task — ` +
  "SolveX ignores your final reply text. It checks your submission and, if something is missing, tells you what; " +
  `fix it and call \`${tool}\` again.\n`;

// ── 评审 ────────────────────────────────────────────────────────────────

export const REVIEW_TOOL = "submit_review";

export function reviewSubmitTool(): SubmitTool {
  return {
    name: REVIEW_TOOL,
    description: "Submit your finished review. This is the only way to finish the review: SolveX saves the `review` " +
      "argument verbatim as the review and ignores your reply text.",
    parameters: {
      type: "object",
      properties: {
        verdict: { type: "string", enum: ["SATISFIED", "NEEDS_REVISION"], description: "Your verdict." },
        review: { type: "string", description: "The complete written review in Markdown: what you checked and the " +
          "evidence (numbers you recomputed, files you read). If the verdict is NEEDS_REVISION, include the sections " +
          "'## Issues Found:' and '## Fix Instructions:' with concrete steps the implementer can follow." },
      },
      required: ["verdict", "review"],
    },
    check(a) {
      const verdict = str(a.verdict).trim().toUpperCase();
      const body = str(a.review).replace(VERDICT_LINE, "").trim();
      const errs: string[] = [];
      if (verdict !== "SATISFIED" && verdict !== "NEEDS_REVISION") errs.push('`verdict` must be "SATISFIED" or "NEEDS_REVISION".');
      if (body.length < MIN_REVIEW_CHARS)
        errs.push(`\`review\` must be the complete written review (at least ${MIN_REVIEW_CHARS} characters; got ${body.length}): ` +
          "what you checked and the evidence.");
      if (verdict === "NEEDS_REVISION" && !/fix instructions/i.test(body))
        errs.push("A NEEDS_REVISION review must include a '## Fix Instructions:' section with concrete steps.");
      return errs.length ? errs.join("\n") : null;
    },
  };
}

/** 被接受的评审提交 → 落盘的评审全文（结论行放最后，与 parseVerdict 的格式一致）。 */
export const formatReview = (a: Record<string, unknown>): string =>
  `${str(a.review).replace(VERDICT_LINE, "").trim()}\n\nVERIFICATION_RESULT: ${str(a.verdict).trim().toUpperCase()}\n`;

// ── 修复 ────────────────────────────────────────────────────────────────

export const FIX_TOOL = "submit_fix";

/**
 * 修复可以选择不改（评审也会误判）：不改文件时在 summary 里说明理由即可。改了文件的评审修复必须同时更新
 * results_summary.md（复审读的是它，否则复审看到的是旧结果）。baseline 是修复请求发出时模型目录的指纹，
 * 编排层据此记录这次修复改了哪些文件（r6：Model 3 三次修复一个文件都没改，当时无从发现）。
 */
export function fixSubmitTool(opts: { modelDir: string; baseline: Fingerprint; requireSummary: boolean }): SubmitTool {
  return {
    name: FIX_TOOL,
    description: "Submit your fix. This is the only way to finish. If you conclude a requested change is wrong or " +
      "unnecessary, you may leave the files unchanged and explain why in `summary`" +
      (opts.requireSummary ? "; if you change files, also update results_summary.md" : "") + ".",
    parameters: {
      type: "object",
      properties: {
        summary: { type: "string", description: "What you changed and why, file by file, and how the key numbers changed — " +
          "or, if you changed nothing, why no change is needed." },
      },
      required: ["summary"],
    },
    check(a) {
      const errs: string[] = [];
      if (str(a.summary).trim().length < MIN_FIX_SUMMARY_CHARS)
        errs.push(`\`summary\` must say what you changed and why, or why no change is needed (at least ${MIN_FIX_SUMMARY_CHARS} characters).`);
      const changed = changedFiles(opts.baseline, fingerprint(opts.modelDir));
      if (changed.length && opts.requireSummary && !changed.includes("results_summary.md"))
        errs.push(`results_summary.md is unchanged. Update ${opts.modelDir}/results_summary.md so it reflects the ` +
          "revised code and numbers — the next review reads that file.");
      return errs.length ? errs.join("\n") : null;
    },
  };
}

/** 修复基线落盘：中断后续跑时沿用请求发出时的指纹，不会把崩溃前已做的改动当成原样。 */
export function fixBaseline(file: string, modelDir: string): Fingerprint {
  if (existsSync(file)) {
    try { return JSON.parse(readFileSync(file, "utf-8")) as Fingerprint; } catch { /* 损坏就重拍 */ }
  }
  const fp = fingerprint(modelDir);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(fp));
  return fp;
}

// ── 论文 ────────────────────────────────────────────────────────────────

export const PAPER_TOOL = "submit_paper";
export const MEMO_FILE = "memo.tex";

/**
 * 论文以 submit_paper 结束。题面要求备忘录时，备忘录正文是必填参数（r6：论文写完了，备忘录没写），
 * 由 SolveX 写成 memo.tex 并插到 \end{document} 前（论文里已有备忘录一节时不重复插入）。
 */
export function paperSubmitTool(opts: { paperPath: string; modelCount: number; problem?: string }): SubmitTool {
  const needsMemo = memoRequired(opts.problem);
  return {
    name: PAPER_TOOL,
    description: "Submit the finished paper. This is the only way to finish: SolveX checks main.tex for every model " +
      "section, a real abstract, a conclusion, no placeholders and a complete document" +
      (needsMemo ? ", and inserts the memo you pass here as its own section" : "") + ".",
    parameters: needsMemo ? {
      type: "object",
      properties: {
        memo_title: { type: "string", description: "Short title, e.g. 'To the Producers'. SolveX prefixes it with 'Memorandum'." },
        memo: { type: "string", description: "The complete memo the problem statement asks for, as LaTeX body text " +
          "(no \\section, no preamble). Use the paper's actual numbers and recommendations." },
      },
      required: ["memo"],
    } : { type: "object", properties: {} },
    check(a) {
      if (!existsSync(opts.paperPath)) return `${opts.paperPath} does not exist yet. Write the paper first.`;
      const tex = readFileSync(opts.paperPath, "utf-8");
      const errs = paperGaps(tex, { modelCount: opts.modelCount }).map((g) => `main.tex is missing ${g}.`);
      if (needsMemo) {
        const memo = str(a.memo).trim();
        if (memo.length < MIN_MEMO_CHARS)
          errs.push(`\`memo\` must be the complete memo the problem asks for (at least ${MIN_MEMO_CHARS} characters; got ${memo.length}).`);
        const ph = findPlaceholder(memo);
        if (ph) errs.push(`\`memo\` contains placeholder text "${ph}".`);
      }
      if (errs.length) return errs.join("\n");
      if (needsMemo) insertMemo(opts.paperPath, tex, str(a.memo_title).trim(), str(a.memo).trim());
      return null;
    },
  };
}

function insertMemo(paperPath: string, tex: string, title: string, memo: string): void {
  const heading = `Memorandum${title ? `: ${title.replace(/^memo(randum)?\s*[:\-–]?\s*/i, "")}` : ""}`;
  writeFileSync(join(dirname(paperPath), MEMO_FILE), `\\clearpage\n\\section*{${heading}}\n${memo}\n`);
  const hasMemo = [...tex.matchAll(/\\section\*?\{([^}]*)\}/g)].some((m) => /\bmemo(randum)?\b/i.test(m[1]));
  if (hasMemo || /\\input\{memo(\.tex)?\}/.test(tex)) return;
  writeFileSync(paperPath, tex.replace(/\\end\{document\}(?![\s\S]*\\end\{document\})/, "\\input{memo}\n\\end{document}"));
}
