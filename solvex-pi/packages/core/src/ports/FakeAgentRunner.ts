import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, relative, sep } from "node:path";
import type { AgentRunner, RunRequest, RunResult } from "./AgentRunner.js";
import { DIR, SHARED_DATA_DIR } from "../workspace/paths.js";

/** submit：提交工具的参数；false 表示这次不调用提交工具；缺省按工具名和回复文字自动生成（fakeSubmitArgs）。 */
export type FakeOutcome = { text?: string; files?: Record<string, string>; fail?: string;
                            submit?: Record<string, unknown> | false };
export type FakeHandler = (req: RunRequest) => FakeOutcome | undefined;

export type FakeOptions = {
  models?: string[];
  handlers?: FakeHandler[];
  failTaskIds?: string[];
  delayMs?: number;
  onCall?: (req: RunRequest) => void;
  /** 演示模式：合成 Pi 原生 thinking/turn/tool/usage 事件，供 WebUI 三视图展示。 */
  synthetic?: boolean;
};

const SUMMARY = [
  "# Model Results Summary", "", "## Key Numerical Results", "Objective value: 42.0", "",
  "## Sanity Checks", "All sums and ranges verified.", "", "## Model Parameters", "alpha = 0.5", "",
  "## Data Files Generated", "results.csv (10 rows, 3 columns)", "", "## Figures",
  "fig1.png: convergence curve", "", "## Issues or Limitations", "None.", "",
  "VERIFICATION_RESULT: SATISFIED", "",
].join("\n");

/** 有正文的评审（编排层要求评审正文 ≥ MIN_REVIEW_CHARS，否则追问书面评审）。 */
export const FAKE_REVIEW_BODY = [
  "# Review", "",
  "Checked: re-ran run.py in the scratch directory and compared results.json field by field (all match).",
  "Recomputed the objective from results.csv: 42.0, consistent with the summary.",
  "Parameter alpha = 0.5 matches the plan; constraint sums verified on all 10 rows.",
  "Figures fig1.png and the convergence data agree with the reported values.",
  "Limitations are stated in the summary; no unsupported claims found.", "",
].join("\n");
export const FAKE_REVIEW_OK = `${FAKE_REVIEW_BODY}\nVERIFICATION_RESULT: SATISFIED\n`;

export const FAKE_MEMO = "Dear Producers, the three models agree on the main recommendation. ".repeat(20);

/** 模拟模型调用提交工具时给的参数（ADR-0015）：评审的结论和正文取自回复文字。 */
export function fakeSubmitArgs(tool: string, text: string): Record<string, unknown> {
  if (tool === "submit_review") {
    const v = /VERIFICATION_RESULT:\s*(SATISFIED|NEEDS_REVISION)/i.exec(text)?.[1]?.toUpperCase() ?? "";
    return { verdict: v, review: text };
  }
  if (tool === "submit_paper") return { memo_title: "To the Producers", memo: FAKE_MEMO };
  return { summary: "Applied the requested fix, re-ran run.py and updated results_summary.md." };
}

/** 按 RunRequest.submit 执行一次提交，返回被接受的参数。 */
export async function fakeSubmit(req: RunRequest, text: string, args?: Record<string, unknown> | false):
    Promise<Record<string, unknown> | undefined> {
  if (!req.submit || args === false) return undefined;
  const a = args ?? fakeSubmitArgs(req.submit.name, text);
  return (await req.submit.check(a)) === null ? a : undefined;
}

/** 0 次模型调用即可跑通完整四阶段的 FakeRunner（T2.1 / CP2）。
 *  默认按 role + taskId 自动落盘兼容产物；可用 handlers 覆盖任意一次调用。 */
export class FakeAgentRunner implements AgentRunner {
  readonly calls: RunRequest[] = [];
  constructor(private readonly opts: FakeOptions = {}) {}

  async run(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    if (signal?.aborted) throw new Error("aborted");
    this.calls.push(req);
    this.opts.onCall?.(req);
    if (this.opts.delayMs) await new Promise((r) => setTimeout(r, this.opts.delayMs));
    if (signal?.aborted) throw new Error("aborted");

    if (this.opts.failTaskIds?.includes(req.taskId ?? "")) throw new Error(`fake failure: ${req.taskId}`);
    if (this.opts.synthetic) this.emitSynthetic(req);

    const override = this.opts.handlers?.map((h) => h(req)).find((x) => x !== undefined);
    const outcome: FakeOutcome = override ?? this.auto(req);
    if (outcome.fail) throw new Error(outcome.fail);

    const files: Record<string, string> = outcome.files ?? {};
    for (const [rel, content] of Object.entries(files)) {
      const abs = join(req.cwd, rel);
      mkdirSync(abs.slice(0, abs.lastIndexOf(sep)), { recursive: true });
      writeFileSync(abs, content);
    }
    const text = outcome.text ?? SUMMARY;
    const submitted = await fakeSubmit(req, text, outcome.submit);
    return {
      text,
      artifacts: Object.keys(files).map((p) => relative(req.cwd, join(req.cwd, p))),
      usage: { input: 100, output: 50, cost: 0.01 },
      settled: true,
      ...(submitted ? { submitted } : {}),
    };
  }

  /** 合成 §4.6 内层事件：让无凭据演示也能展示思考过程 / 运行阶段 / 用量条。 */
  private emitSynthetic(req: RunRequest): void {
    const taskId = req.taskId ?? "unknown";
    const e = (ev: Record<string, unknown>) => req.onEvent?.({ ...ev, ts: Date.now() } as any);
    const block = `${taskId}:0`;
    const thinking = "分析问题结构，识别核心数学挑战，设计多模型方案。";
    e({ type: "lifecycle", taskId, state: "agent_start" });
    e({ type: "model", taskId, provider: "demo", model: "fake-runner", thinkingLevel: req.thinkingLevel });
    e({ type: "turn", taskId, state: "start", turn: 1 });
    e({ type: "thinking", taskId, state: "start", blockId: block, contentIndex: 0 });
    for (const delta of ["分析问题结构，", "识别核心数学挑战，", "设计多模型方案。"])
      e({ type: "thinking", taskId, state: "delta", blockId: block, contentIndex: 0, delta });
    e({ type: "thinking", taskId, state: "end", blockId: block, contentIndex: 0, content: thinking });
    e({ type: "output", taskId, state: "delta", blockId: `${taskId}:1`, contentIndex: 1, delta: "正在写入产物…" });
    e({ type: "output", taskId, state: "end", blockId: `${taskId}:1`, contentIndex: 1, content: "正在写入产物…" });
    e({ type: "tool", taskId, toolCallId: `${taskId}-w1`, name: "write", state: "start", args: { path: "output" } });
    e({ type: "tool", taskId, toolCallId: `${taskId}-w1`, name: "write", state: "end", result: "ok", isError: false });
    e({ type: "usage", taskId, input: 120, output: 80, cacheRead: 0, cacheWrite: 0,
         totalTokens: 200, cost: 0.002, cumulative: false });
    e({ type: "turn", taskId, state: "end", turn: 1 });
    e({ type: "lifecycle", taskId, state: "agent_end" });
    e({ type: "lifecycle", taskId, state: "agent_settled" });
  }

  private modelOf(req: RunRequest): string | undefined {
    return req.taskId?.match(/:(model_[a-z0-9_]+)/)?.[1];
  }

  /** 自动产出与旧 workspace 契约兼容的文件（§2.5）。 */
  private auto(req: RunRequest): FakeOutcome {
    const isReview = req.taskId?.startsWith("P2-REVIEW") || /reviewing the implementation results/i.test(req.task);
    const isPlan = req.taskId === "P1" || (!isReview && req.role === "modeling" && /Master Plan/i.test(req.task));

    if (isPlan) {
      const models = this.opts.models ?? ["Model 1", "Model 2", "Model 3"];
      const plan = ["# Master Plan", "", "## Overview", "Multi-model strategy", "",
        ...models.flatMap((m, i) => [
          `## ${m}: Approach ${i + 1}`, "### Purpose", "Solve a sub-problem", "",
          "### Mathematical Formulation", "min f(x) s.t. Ax <= b", "",
          "### Solution Strategy", "Use scipy.optimize.linprog", "",
          "### Expected Outputs", "results.csv and fig1.png", "",
          "### Validation", "Check constraints", "",
        ]),
        "## Integration", "Combine the model outputs.", ""].join("\n");
      return { text: "Master Plan written. VERIFICATION_RESULT: SATISFIED",
               files: { [`${DIR.modeling}/master_plan.md`]: plan,
                        [`${SHARED_DATA_DIR}/panel.csv`]: "season,week,celebrity,judge_total\n1,1,A,20\n",
                        [`${SHARED_DATA_DIR}/data_dictionary.md`]: "# Data dictionary\n\n- judge_total: sum of judge scores\n",
                        [`${SHARED_DATA_DIR}/checks.md`]: "- 1 row, 4 columns: OK\n",
                        [`${SHARED_DATA_DIR}/prep_data.py`]: "print('prep')\n" } };
    }
    if (isReview) {
      const m = this.modelOf(req) ?? "model_1";
      return { text: FAKE_REVIEW_OK,
               files: { [`${DIR.modeling}/${m}_review.md`]: FAKE_REVIEW_OK } };
    }
    if (req.role === "writing") {
      // 通过论文完整性门禁：每个模型一节 + 结论 + 备忘录（题面要求时检查）+ \end{document}
      const models = this.opts.models ?? ["Model 1", "Model 2", "Model 3"];
      const body = models.map((_m, i) => `\\section{Model ${i + 1}: Fake}\nResults.\n`).join("");
      return { text: "Paper written.",
               files: { [`${DIR.paper}/main.tex`]: "\\documentclass{article}\n\\begin{document}\n\\begin{abstract}\n" +
                 "Fake abstract summarising the models, the data, the results and the recommendations. ".repeat(5) +
                 "\n\\end{abstract}\n\\section{Introduction}\nHello\n" +
                 body + "\\section{Conclusion}\nDone.\n\\section*{Memo to Producers}\nAdvice.\n\\end{document}\n" } };
    }
    // programming / fix / revision
    const m = this.modelOf(req) ?? "model_1";
    const base = `${DIR.programming}/${m}`;
    // 修复调用要真的改文件、更新摘要（submit_fix 的检查）。
    const call = req.journal?.call ?? "";
    const revision = /^(fix|repro)-/.test(call) ? { [`${base}/fix_log.md`]: `${call}\n` } : {};
    return {
      text: "VERIFICATION_RESULT: SATISFIED",
      files: {
        [`${base}/model.py`]: "import numpy as np\nprint(42.0)\n",
        // 结果契约（ADR-0014）：run.py 能重新生成与交付一致的 results.json
        [`${base}/run.py`]: "import json\njson.dump({\"objective\": 42.0, \"alpha\": 0.5}, open(\"results.json\", \"w\"))\n",
        [`${base}/results.json`]: JSON.stringify({ objective: 42.0, alpha: 0.5 }),
        [`${base}/results_summary.md`]: Object.keys(revision).length ? `${SUMMARY}\nRevision: ${call}\n` : SUMMARY,
        ...revision,
        [`${base}/results.csv`]: "id,probability\n1,0.2\n2,0.3\n",
        [`${base}/figures/fig1.png`]: "fake-png",
        [`${base}/handoff.json`]: JSON.stringify({ status: "satisfied", issues: [],
          fixInstructions: "", summaryPath: `${base}/results_summary.md` }),
      },
    };
  }
}
