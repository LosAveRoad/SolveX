import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { paperGaps } from "@solvex/core";

const ABS = "\\begin{abstract}\n" + "We estimate weekly fan votes and compare aggregation rules. ".repeat(6) + "\n\\end{abstract}\n";
const full = (n: number, memo = true) => "\\documentclass{article}\\begin{document}\n" + ABS + "\\section{Introduction}\n" +
  Array.from({ length: n }, (_, i) => `\\section{Model ${i + 1}: X}\n`).join("") +
  "\\section{Conclusion}\n" + (memo ? "\\section*{Appendix A: Memo to DWTS Producers}\n" : "") + "\\end{document}\n";

describe("P4 论文完整性门禁（r6 实测回归：半篇论文被当成交付）", () => {
  it("完整论文没有缺口", () => {
    expect(paperGaps(full(3), { modelCount: 3, problem: "include a one- to two-page memo" })).toEqual([]);
  });
  it("r6 的半篇论文：缺 Model 2/3、结论与备忘录", () => {
    const tex = "\\begin{document}\\section{Introduction}\\section{Model 1: Constrained-Ordinal Bayesian}\\end{document}";
    const g = paperGaps(tex, { modelCount: 3, problem: "Produce a report ... and include a memo" });
    expect(g).toHaveLength(5);
    expect(g.join("|")).toMatch(/Model 2.*Model 3.*Conclusion.*abstract.*memo/);
  });
  it("截断的文件：缺 \\end{document}", () => {
    expect(paperGaps(full(2).replace("\\end{document}", ""), { modelCount: 2 })).toEqual(["\\end{document} (the file is truncated)"]);
  });
  it("题面没要求备忘录就不检查；\\section* 与大小写都认", () => {
    expect(paperGaps(full(1, false), { modelCount: 1, problem: "Write a paper." })).toEqual([]);
    expect(paperGaps(ABS + "\\section*{model 1}\\section{Conclusions and Future Work}\\end{document}", { modelCount: 1 })).toEqual([]);
  });
  it("Model 1 不会被 Model 10 误认", () => {
    expect(paperGaps(ABS + "\\section{Model 10}\\section{Conclusion}\\end{document}", { modelCount: 1 })).toHaveLength(1);
  });
  it("摘要是占位符（r6 实测 PHOLDER）或缺失：列为缺口", () => {
    const ph = full(1, false).replace(ABS, "\\begin{abstract}\nPHOLDER\n\\end{abstract}\n");
    expect(paperGaps(ph, { modelCount: 1 })).toEqual(['a real abstract (the current one is only "PHOLDER")',
      'placeholder text "PHOLDER" replaced with real content']);
    expect(paperGaps(full(1, false).replace(ABS, ""), { modelCount: 1 })[0]).toMatch(/an abstract/);
  });
  it("正文里的占位符标记列为缺口；普通单词 placeholder 与 LaTeX 注释不算", () => {
    expect(paperGaps(full(1, false).replace("\\section{Conclusion}", "\\section{Conclusion}\nTODO: fill in"), { modelCount: 1 }))
      .toEqual(['placeholder text "TODO" replaced with real content']);
    expect(paperGaps(full(1, false).replace("\\section{Conclusion}", "\\section{Conclusion}\nflags rather than placeholder floors % TODO later"),
      { modelCount: 1 })).toEqual([]);
  });
  it("此前几轮完整的基准论文都能通过（r3/r4 有备忘录，r5 没有）", () => {
    const root = "bench/sessions";
    const cases: [string, boolean][] = [["r3-c3-review-mwntpmop", true], ["r4-c3-journal-mwodcgan", true], ["r5-c3-reviewloop-mwofdv75", false]];
    for (const [dir, hasMemoSection] of cases) {
      const p = `${root}/${dir}/04_paper/main.tex`;
      if (!existsSync(p)) continue;
      const g = paperGaps(readFileSync(p, "utf-8"), { modelCount: 3, problem: "include a memo" });
      if (hasMemoSection && dir.startsWith("r3")) expect(g).toEqual([]);
      if (!hasMemoSection) expect(g).toEqual(["the memo required by the problem statement, as its own \\section"]);
    }
  });
});
