import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  summarizeArtifacts, hasRealArtifacts, ensureSummary, validateModelOutput,
  aggregate, prepareWorkspace,
} from "@solvex/core";
import { checkPythonDeps } from "@solvex/pi-runtime";

const dir = () => mkdtempSync(join(tmpdir(), "solvex-artifacts-"));

/**
 * ADR-0009 回归：真实 DeepSeek 跑 2026 MCM C 时，模型产出了 2777 行 CSV 却没写
 * results_summary.md；旧兜底摘要写 "⚠ Not available."，P3 只聚合摘要，P4 便把
 * 「计算未完成」写进论文。这里锁死「真实产物必须进入下游」这条链。
 */
describe("ADR-0009 真实产物传递", () => {
  it("summarizeArtifacts 提取 CSV 表头、行数与数值统计", () => {
    const d = dir();
    writeFileSync(join(d, "estimates.csv"),
      "season,week,score\n1,1,0.5\n1,2,0.9\n2,1,0.3\n2,2,0.7\n");
    writeFileSync(join(d, "model.py"), "print(1+1)\n");
    const s = summarizeArtifacts(d);
    expect(s).toContain("estimates.csv");
    expect(s).toContain("data_rows=4");
    expect(s).toContain("score:");
    expect(s).toContain("model.py");
    expect(hasRealArtifacts(d)).toBe(true);
  });

  it("ensureSummary 用真实产物证据替代空占位", () => {
    const d = dir();
    writeFileSync(join(d, "fan_vote_estimates.csv"), "season,pF_med\n1,0.13\n1,0.18\n");
    const body = ensureSummary(d, "Model 1");
    expect(body).toContain("Artifacts discovered by SolveX");
    expect(body).toContain("fan_vote_estimates.csv");
    expect(body).not.toContain("no validated results available");
    expect(body).not.toContain("⚠ Not available.");
    for (const h of ["## Key Numerical Results", "## Sanity Checks", "## Model Parameters",
                     "## Data Files Generated", "## Figures", "## Issues or Limitations"])
      expect(body).toContain(h);
  });

  it("旧式空占位摘要被判为 PLACEHOLDER_SUMMARY critical", () => {
    const d = dir();
    writeFileSync(join(d, "model.py"), "print(1)\n");
    mkdirSync(join(d, "figures"));
    writeFileSync(join(d, "results_summary.md"),
      "# Model 1 Results Summary (auto-generated)\n## Status\n" +
      "⚠ Agent did not write results_summary.md — no validated results available.\n" +
      "## Key Numerical Results\n⚠ Not available.\n");
    const issues = validateModelOutput(d);
    expect(issues.some((i) => i.code === "PLACEHOLDER_SUMMARY" && i.severity === "critical"))
      .toBe(true);
  });

  it("aggregate 把产物清单写入 all_results_summary.md", () => {
    const root = dir();
    const ws = prepareWorkspace({ root, sessionId: "aggregate-test", problem: "p" });
    const modelDir = join(ws.paths.programming, "model_1");
    mkdirSync(modelDir, { recursive: true });
    writeFileSync(join(modelDir, "weekly_consistency.csv"),
      "season,week,rhat\n1,1,1.01\n1,2,1.02\n");
    const { content } = aggregate(ws, ["Model 1"]);
    expect(content).toContain("Artifacts discovered by SolveX");
    expect(content).toContain("weekly_consistency.csv");
    expect(content).toContain("rhat");
  });

  it("checkPythonDeps 可探测绘图依赖且不抛错", () => {
    const missing = checkPythonDeps(["matplotlib"]);
    expect(Array.isArray(missing)).toBe(true);
    expect(missing.every((m) => typeof m === "string")).toBe(true);
  });
});
