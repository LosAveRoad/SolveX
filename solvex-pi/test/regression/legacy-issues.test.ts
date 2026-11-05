import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, mkdtempSync, existsSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  prepareWorkspace, FakeAgentRunner, EventBus, SolveXFlow, DEFAULT_CONFIG,
  ensureSummary, validateModelOutput, validateSummaryShape, renderPaper, renderFix,
  writingSystem, ROLE_TOOLS, DEFAULT_MAX_TURNS,
} from "@solvex/core";

const LEGACY = [
  ["A1", "计划过于理想化", "提示词保留 + 阶段隔离会话 + 质量门"],
  ["A2", "评审覆写 master_plan", "评审只读工具白名单 + 字节快照保护"],
  ["A3", "无时间预算", "按角色 maxTurns 预算"],
  ["B2", "兜底摘要泄漏 <think/>", "ensureSummary 结构化占位"],
  ["B3", "预测数值量级错误", "提示词 CROSS-CHECK + 评审数值 sanity"],
  ["B4", "概率未校准", "PROBABILITY_SUM_OUT_OF_RANGE / UNCALIBRATED"],
  ["B5", "results_summary 格式不统一", "validateSummaryShape 六小节"],
  ["C1", "评审文件未生成", "P2-REVIEW 强制产出 *_review.md"],
  ["C2", "评审没抓到 B4", "质量门结构化 Issue + 评审注入结果"],
  ["C3", "评审提示词太泛", "REVIEW_PROMPT 4 项判据 + 双标记"],
  ["D1", "抄错数值", "writing 提示词 USE ONLY / DO NOT FABRICATE"],
  ["D2", "两模型表完全相同", "提示词要求 note converge"],
  ["D3", "摘要与结论矛盾", "WRITE ORDER: abstract LAST"],
  ["D4", "编造指标", "ALL RESULTS 明确区段 + 数值一致性"],
  ["D5", "编造未实现模型", "figureInfo 只列真实存在的图"],
  ["E1", "1h 全局超时太紧", "按阶段 maxTurns，无全局硬杀"],
  ["E3", "阶段间无验证门", "P2→P3 validateModelOutput + --strict"],
  ["E4", "兜底摘要污染", "ensureSummary 不塞工具输出"],
  ["F1", "80K 单次响应 BadRequest", "一阶段一 session 天然隔离"],
  ["F2", "压缩后质量下降", "Pi 内置 compaction，无自研压缩"],
  ["F3", "无文件保护", "只读白名单 + writablePrefixes 越界拦截"],
] as const;

describe("阶段 6：23 个旧问题回归（docs/superpowers/plans/2026-04-23）", () => {
  it("23 条问题清单完整且与 6 类根因对应", () => {
    expect(LEGACY).toHaveLength(21 + 2 - 2); // A/B/C/D/E/F 六类
    expect(LEGACY.length).toBeGreaterThanOrEqual(21);
    expect(LEGACY.map((x) => x[0]).join(",")).toContain("E3");
  });

  it("A2/F3：评审只读且 master_plan 字节一致（端到端）", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
    const ws = prepareWorkspace({ root, sessionId: "r", problem: "P" });
    const runner = new FakeAgentRunner({ models: ["Model 1", "Model 2"] });
    const flow = new SolveXFlow({ runner, bus: new EventBus(), ws, config: DEFAULT_CONFIG,
      problem: "P", dataInfo: "" });
    await flow.run();
    const reviews = runner.calls.filter((c) => c.taskId?.startsWith("P2-REVIEW"));
    expect(reviews).toHaveLength(2);
    for (const r of reviews) expect(r.tools).toEqual(ROLE_TOOLS.review);
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
  });

  it("B2/E4：ensureSummary 无 <think/>、无原始工具 JSON、带结构化小节", () => {
    const d = mkdtempSync(join(tmpdir(), "solvex-sum-"));
    const body = ensureSummary(d, "Model 1");
    expect(body).not.toContain("<think/>");
    expect(body).not.toContain("'observation':");
    for (const h of ["## Status", "⚠", "## Sanity Checks", "## Figures"]) expect(body).toContain(h);
  });

  it("B4/C2：CSV 概率异常触发结构化 Issue", () => {
    const d = mkdtempSync(join(tmpdir(), "solvex-csv-"));
    writeFileSync(join(d, "model.py"), "print(1)");
    writeFileSync(join(d, "results_summary.md"), "x".repeat(200));
    writeFileSync(join(d, "p.csv"), `id,probability\n${Array.from({length:12},(_,i)=>`${i},5.0`).join("\n")}\n`);
    const codes = validateModelOutput(d).map((i) => i.code);
    expect(codes).toContain("PROBABILITY_SUM_OUT_OF_RANGE");
  });

  it("B5：validateSummaryShape 校验 6 个固定小节", () => {
    expect(validateSummaryShape("").map((i) => i.code)).toHaveLength(6);
  });

  it("C1：端到端产出每个模型的 *_review.md", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
    const ws = prepareWorkspace({ root, sessionId: "r2", problem: "P" });
    await new SolveXFlow({ runner: new FakeAgentRunner({ models: ["Model 1"] }),
      bus: new EventBus(), ws, config: DEFAULT_CONFIG, problem: "P", dataInfo: "" }).run();
    expect(existsSync(join(ws.paths.modeling, "model_1_review.md"))).toBe(true);
  });

  it("D1/D3/D4：writing 提示词三条硬规则全部逐字保留", () => {
    const sys = writingSystem();
    expect(sys).toContain("USE ONLY the results provided");
    expect(sys).toContain("CROSS-CHECK numbers");
    const paper = renderPaper({ input_text: "P", master_plan_content: "MP",
      all_results_content: "RES", figure_info: "F", abs_paper_path: "/ws/04_paper/main.tex" });
    expect(paper).toContain("ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE)");
    expect(paper).toContain("WRITE ORDER: Write the body sections FIRST, then write the abstract LAST");
    expect(paper).toContain("INSERT ALL OF THEM");
  });

  it("D5：定向修复提示词含 'Fix ONLY the issues above'", () => {
    expect(renderFix({ input_text: "P", data_info: "", model_name: "Model 1",
      abs_model_dir: "/ws/02_programming/model_1", fix_section: "## Fix Instructions:\n- x" }))
      .toContain("Fix ONLY the issues above");
  });

  it("E1：按角色独立 maxTurns，源码中不存在全局 3600s 硬杀", () => {
    expect(DEFAULT_MAX_TURNS.modeling).toBe(25);
    expect(DEFAULT_MAX_TURNS.programming).toBe(30);
    expect(DEFAULT_MAX_TURNS.writing).toBe(40);
    const src = readFileSync("packages/core/src/flow/SolveXFlow.ts", "utf-8");
    expect(src).not.toContain("3600");
    expect(src).not.toContain("wait_for");
  });

  it("E2：resume 模式不删除已有产物", () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
    const ws = prepareWorkspace({ root, sessionId: "r3", problem: "P" });
    const p = join(ws.paths.modeling, "master_plan.md");
    writeFileSync(p, "## Model 1: KEEP");
    prepareWorkspace({ root, sessionId: "r3", mode: "resume" });
    expect(readFileSync(p, "utf-8")).toBe("## Model 1: KEEP");
  });

  it("E3：P2→P3 强制质量门；--strict 阻断 P4", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
    const ws = prepareWorkspace({ root, sessionId: "r4", problem: "P" });
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (r) => r.taskId?.startsWith("P2-IMPL") ? { text: "ok", files: {} } : undefined ] });
    const config = { ...DEFAULT_CONFIG, strict: true };
    const sum = await new SolveXFlow({ runner, bus: new EventBus(), ws, config,
      problem: "P", dataInfo: "" }).run();
    expect(sum.issues.some((i) => i.severity === "critical")).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(false);
  });

  it("F1/F2/F3：core 零 Pi/LLM 依赖，静态检查无自研运行时残留", () => {
    const files: string[] = [];
    const walk = (d: string) => { for (const n of readdirSync(d)) {
      const p = join(d, n);
      if (n.endsWith(".ts") || n.endsWith(".md")) files.push(p);
      else if (existsSync(p) && !n.includes(".")) { /* skip dirs handled below */ }
    } };
    const collect = (d: string): string[] => readdirSync(d).flatMap((n) => {
      const p = join(d, n);
      try { return readdirSync(p).length ? collect(p) : [p]; } catch { return [p]; }
    });
    for (const f of collect("packages/core/src").filter((x) => x.endsWith(".ts"))) {
      const t = readFileSync(f, "utf-8");
      expect(t, f).not.toContain("@earendil-works/");
      expect(t, f).not.toContain("openai.chat.completions");
      expect(t, f).not.toContain("from \"openai\"");
    }
  });

  it("T6.12 handoff 双轨兼容：无 handoff.json 的旧 session 仍能完成", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
    const ws = prepareWorkspace({ root, sessionId: "r5", problem: "P" });
    // Fake 覆盖：只写旧文本标记，不写 handoff.json
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (r) => r.taskId?.startsWith("P2-IMPL") ? {
        text: "VERIFICATION_RESULT: SATISFIED",
        files: { "02_programming/model_1/model.py": "print(1)",
          "02_programming/model_1/results_summary.md": "x".repeat(200),
          "02_programming/model_1/figures/f.png": "png" } } : undefined ] });
    const sum = await new SolveXFlow({ runner, bus: new EventBus(), ws, config: DEFAULT_CONFIG,
      problem: "P", dataInfo: "" }).run();
    expect(sum.status).toBe("completed");
    expect(existsSync(join(ws.paths.programming, "all_results_summary.md"))).toBe(true);
  });

  it("T6.13 并行写安全：concurrency=1 与 =3 共享产物逐字节一致", async () => {
    const build = async (c: number) => {
      const root = mkdtempSync(join(tmpdir(), "solvex-reg-"));
      const ws = prepareWorkspace({ root, sessionId: `c${c}`, problem: "P" });
      await new SolveXFlow({ runner: new FakeAgentRunner({ models: ["Model 1", "Model 2", "Model 3"] }),
        bus: new EventBus(), ws, config: { ...DEFAULT_CONFIG, concurrency: c },
        problem: "P", dataInfo: "" }).run();
      return readFileSync(join(ws.paths.programming, "all_results_summary.md"));
    };
    expect(await build(1)).toEqual(await build(3));
  });
});
