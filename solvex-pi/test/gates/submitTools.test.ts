import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  reviewSubmitTool, formatReview, fixSubmitTool, fixBaseline, fingerprint, paperSubmitTool, parseVerdict,
  MIN_REVIEW_CHARS, MIN_MEMO_CHARS,
} from "@solvex/core";

const BODY = "Checked results.json against a re-run of run.py; all 12 fields match. ".repeat(8);

describe("submit_review（ADR-0015）", () => {
  const t = reviewSubmitTool();
  it("空评审、只有结论行、结论不合法都不接受，原因写清楚", async () => {
    expect(await t.check({ verdict: "SATISFIED", review: "" })).toMatch(new RegExp(`at least ${MIN_REVIEW_CHARS}`));
    expect(await t.check({ verdict: "SATISFIED", review: "VERIFICATION_RESULT: SATISFIED" })).toMatch(/got 0/);
    expect(await t.check({ verdict: "looks good", review: BODY })).toMatch(/SATISFIED" or "NEEDS_REVISION/);
    expect(await t.check({})).toBeTruthy();
  });
  it("NEEDS_REVISION 必须带修复步骤", async () => {
    expect(await t.check({ verdict: "NEEDS_REVISION", review: BODY })).toMatch(/Fix Instructions/);
    expect(await t.check({ verdict: "needs_revision", review: `${BODY}\n## Issues Found:\n1. x\n## Fix Instructions:\n1. y` })).toBeNull();
  });
  it("落盘格式：正文里自带的结论行去掉，以提交的结论结尾，parseVerdict 读得出修复意见", () => {
    const text = formatReview({ verdict: "NEEDS_REVISION",
      review: `${BODY}\nVERIFICATION_RESULT: SATISFIED\n## Issues Found:\n1. x\n## Fix Instructions:\nrecompute` });
    expect(text.match(/VERIFICATION_RESULT/g)).toHaveLength(1);
    const v = parseVerdict({ text });
    expect(v.status).toBe("needs_revision");
    expect(v.fixInstructions).toContain("recompute");
  });
});

describe("submit_fix：可以选择不改（说明理由）；改了代码就要更新摘要", () => {
  const setup = () => {
    const dir = mkdtempSync(join(tmpdir(), "solvex-fix-"));
    writeFileSync(join(dir, "model.py"), "print(1)\n");
    writeFileSync(join(dir, "results_summary.md"), "# s\n");
    return dir;
  };
  const SUMMARY = "Recomputed the vote share with the normalised weights; Jerry Rice p_win 1.0 -> 0.31.";
  it("一个文件都没改：说明了理由就接受（评审也会误判）；理由太短不接受", async () => {
    const dir = setup();
    const t = fixSubmitTool({ modelDir: dir, baseline: fingerprint(dir), requireSummary: true });
    expect(await t.check({ summary: "The reviewer's sum is wrong: the two shares are from different weeks." })).toBeNull();
    expect(await t.check({ summary: "no" })).toMatch(/why no change is needed/);
  });
  it("评审修复只改代码、没更新摘要：不接受；都改了才接受；摘要说明太短也不接受", async () => {
    const dir = setup();
    const t = fixSubmitTool({ modelDir: dir, baseline: fingerprint(dir), requireSummary: true });
    writeFileSync(join(dir, "model.py"), "print(2)\n");
    expect(await t.check({ summary: SUMMARY })).toMatch(/results_summary\.md is unchanged/);
    writeFileSync(join(dir, "results_summary.md"), "# s v2\n");
    expect(await t.check({ summary: "fixed" })).toMatch(/summary/);
    expect(await t.check({ summary: SUMMARY })).toBeNull();
  });
  it("复现修复不要求改摘要；内容没变的重写不算改动（不会被要求补摘要）", async () => {
    const dir = setup();
    const t = fixSubmitTool({ modelDir: dir, baseline: fingerprint(dir), requireSummary: false });
    writeFileSync(join(dir, "results.json"), "{}");                     // 新文件
    expect(await t.check({ summary: SUMMARY })).toBeNull();
    const dir2 = setup();
    const t2 = fixSubmitTool({ modelDir: dir2, baseline: fingerprint(dir2), requireSummary: true });
    writeFileSync(join(dir2, "model.py"), "print(1)\n");               // 同样内容重写
    expect(await t2.check({ summary: SUMMARY })).toBeNull();
  });
  it("基线落盘：续跑时沿用修复请求发出时的指纹", () => {
    const dir = setup();
    const file = join(mkdtempSync(join(tmpdir(), "solvex-base-")), "x.fix-1.baseline.json");
    const b1 = fixBaseline(file, dir);
    writeFileSync(join(dir, "model.py"), "print(9)\n");                 // 崩溃前已经改了
    expect(fixBaseline(file, dir)).toEqual(b1);
  });
});

describe("submit_paper：完整性门禁 + 备忘录参数", () => {
  const ABS = "\\begin{abstract}\n" + "We estimate weekly fan votes and compare rules. ".repeat(8) + "\n\\end{abstract}\n";
  const paper = (models: number, extra = "") => "\\documentclass{article}\n\\begin{document}\n" + ABS +
    Array.from({ length: models }, (_, i) => `\\section{Model ${i + 1}: X}\n`).join("") +
    "\\section{Conclusion}\nDone.\n" + extra + "\\end{document}\n";
  const MEMO = "Dear producers, we recommend the rank-based rule. ".repeat(30);
  const setup = (tex?: string) => {
    const dir = mkdtempSync(join(tmpdir(), "solvex-paper-"));
    const p = join(dir, "main.tex");
    if (tex !== undefined) writeFileSync(p, tex);
    return { dir, p };
  };
  it("没有论文、缺节都不接受，并列出缺口", async () => {
    const a = setup();
    expect(await paperSubmitTool({ paperPath: a.p, modelCount: 3 }).check({})).toMatch(/does not exist/);
    const b = setup(paper(1));
    const r = await paperSubmitTool({ paperPath: b.p, modelCount: 3 }).check({});
    expect(r).toMatch(/Model 2/); expect(r).toMatch(/Model 3/);
  });
  it("题面没要求备忘录：没有参数，论文完整就接受", async () => {
    const { p } = setup(paper(3));
    const t = paperSubmitTool({ paperPath: p, modelCount: 3, problem: "Write a paper." });
    expect(t.parameters.properties).toEqual({});
    expect(await t.check({})).toBeNull();
  });
  it("题面要求备忘录：太短或含占位符不接受；接受后写 memo.tex 并插到 \\end{document} 前（只插一次）", async () => {
    const { dir, p } = setup(paper(3));
    const t = paperSubmitTool({ paperPath: p, modelCount: 3, problem: "Include a one-page memo." });
    expect(await t.check({ memo: "Short." })).toMatch(new RegExp(`at least ${MIN_MEMO_CHARS}`));
    expect(await t.check({ memo: MEMO + " TBD" })).toMatch(/placeholder text "TBD"/);
    expect(existsSync(join(dir, "memo.tex"))).toBe(false);
    expect(await t.check({ memo_title: "Memo: To the Producers", memo: MEMO })).toBeNull();
    expect(readFileSync(join(dir, "memo.tex"), "utf-8")).toMatch(/^\\clearpage\n\\section\*\{Memorandum: To the Producers\}\nDear producers/);
    expect(readFileSync(p, "utf-8")).toMatch(/\\input\{memo\}\n\\end\{document\}\n$/);
    expect(await t.check({ memo: MEMO })).toBeNull();
    expect(readFileSync(p, "utf-8").match(/\\input\{memo\}/g)).toHaveLength(1);
  });
  it("论文里已经有备忘录一节：不重复插入", async () => {
    const { p } = setup(paper(3, "\\section*{Memo to Producers}\nAdvice.\n"));
    expect(await paperSubmitTool({ paperPath: p, modelCount: 3, problem: "memo" }).check({ memo: MEMO })).toBeNull();
    expect(readFileSync(p, "utf-8")).not.toContain("\\input{memo}");
  });
});
