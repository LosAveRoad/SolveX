import { describe, it, expect } from "vitest";
import {
  renderPlan, renderPlanRetry, renderImplement, renderSummaryRetry,
  renderRevision, renderFix, renderPaper,
  modelingSystem, writingSystem, HANDOFF_HINT, PLANNING_POLICY,
  RESULTS_CONTRACT, WORKSPACE_DISCOVERY_POLICY,
} from "@solvex/core";

const V = { input_text: "PROBLEM TEXT", data_info: "DATA INFO\n", master_plan_path: "/ws/01_modeling/master_plan.md",
  model_name: "Model 2", model_plan_section: "## Model 2: X", abs_model_dir: "/ws/02_programming/model_2",
  prev_summary: "PREV", fix_section: "## Fix Instructions:\n- fix a",
  master_plan_content: "MP", all_results_content: "RES", figure_info: "FIG",
  abs_paper_path: "/ws/04_paper/main.tex" };

describe("T1.5 内联 5 段提示词（附录 A）", () => {
  it("plan.ts", () => {
    const s = renderPlan(V);
    expect(s).toContain("PROBLEM:\nPROBLEM TEXT");
    expect(s).toContain("write a multi-model");
    expect(s).toContain("'## Model N: Name' section");
    expect(s).toContain("/ws/01_modeling/master_plan.md");
    expect(renderPlanRetry(V)).toContain("URGENT: Write a multi-model Master Plan NOW");
  });
  it("implement.ts", () => {
    const s = renderImplement(V);
    expect(s).toContain("=== YOUR TASK: Implement Model 2 ===");
    expect(s).toContain("MODEL PLAN:\n## Model 2: X");
    expect(s).toContain("figures/");
    expect(s).toContain("results_summary.md");
    expect(s).toContain("handoff.json");           // D3 双轨增强
  });
  it("revision.ts", () => {
    const s = renderRevision(V);
    expect(s).toContain("(REVISION)");
    expect(s).toContain("PREVIOUS RESULTS:\nPREV");
    expect(s).toContain("handoff.json");
  });
  it("fix.ts", () => {
    const s = renderFix(V);
    expect(s).toContain("(TARGETED REVISION)");
    expect(s).toContain("=== FIX INSTRUCTIONS ===");
    expect(s).toContain("Fix ONLY the issues above");
  });
  it("paper.ts：逐字保留 LaTeX 花括号，占位符正确替换", () => {
    const s = renderPaper(V);
    expect(s).toContain("=== ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE) ===");
    expect(s).toContain("=== AVAILABLE FIGURES (INSERT ALL OF THEM) ===");
    expect(s).toContain("../02_programming/");
    expect(s).toContain("WRITE ORDER: Write the body sections FIRST, then write the abstract LAST");
    // LaTeX 花括号不能被 renderTemplate 误当占位符吃掉
    expect(s).toContain("\\includegraphics[width=0.8\\textwidth]{../02_programming/model_N/figures/figure_name.png}");
    expect(s).toContain("=== ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE) ===\nRES");
    expect(s).not.toContain("{input_text}");
  });
  it("D3 追加句只有一句，不改写原文", () => {
    expect(HANDOFF_HINT.trim().split("\n")).toHaveLength(1);
    expect(HANDOFF_HINT).toContain("the system prefers it over text markers");
  });
  it("ADR-0009：结果契约与工作区发现策略在运行时追加", () => {
    expect(renderImplement(V)).toContain("results_summary.md at the exact path above is MANDATORY");
    expect(renderImplement(V)).toContain("at least ONE publication-quality figure");
    expect(renderImplement(V)).toContain("=== YOUR TASK: Implement Model 2 ==="); // 原模板未改
    expect(renderSummaryRetry({ abs_model_dir: V.abs_model_dir })).toContain("URGENT");
    expect(writingSystem()).toContain("WORKSPACE DISCOVERY POLICY");
    expect(writingSystem()).toContain("EISDIR");
    expect(RESULTS_CONTRACT).toContain("Key Numerical Results");
    expect(WORKSPACE_DISCOVERY_POLICY).toContain("02_programming/");
  });
  it("ADR-0008/0011/0014：P1 策略保留网络规则、不硬编码工具名，并要求先看数据、建共享数据集再写计划", () => {
    for (const s of [renderPlan(V), renderPlanRetry(V), modelingSystem()]) {
      expect(s).toContain("PHASE 1 RUNTIME POLICY");
      expect(s).toContain("such requests are unavailable");
      expect(s).toContain("If a search tool IS listed");
      expect(s).toContain("INSPECT THE DATA");
      expect(s).toContain("BUILD THE SHARED DATASET in 01_modeling/shared_data/");
      expect(s).toContain("data_dictionary.md");
      expect(s).not.toContain("FIRST action");                       // 不再「先写计划、写完即停」
      expect(s).not.toContain("Do not explore the filesystem");
      expect(s).not.toContain("arxiv_search");
    }
    expect(PLANNING_POLICY).not.toMatch(/\b(write|read|bash|grep|find|ls|edit|python_execute)\b/);
    // 内联模板常量（逐字资产）不得被改写
    expect(renderPlan(V)).toContain("write a multi-model");
    expect(renderPlan(V)).toContain("## Model N: Name");
  });
  it("ADR-0014：结果契约要求 run.py + results.json，摘要数字只能抄自 results.json", () => {
    const s = renderImplement(V);
    expect(s).toContain("REPRODUCIBILITY CONTRACT");
    expect(s).toContain("python3 run.py");
    expect(s).toContain("Every number in results_summary.md must be copied from results.json");
  });
});
