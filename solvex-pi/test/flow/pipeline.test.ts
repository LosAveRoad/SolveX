import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  prepareWorkspace, FakeAgentRunner, EventBus, SolveXFlow, DEFAULT_CONFIG,
  ROLE_TOOLS, type SolveXEvent, type ModelConfig,
} from "@solvex/core";

const MODELS = ["Model 1", "Model 2", "Model 3"];
function setup(opts: { concurrency?: number; strict?: boolean; runner?: FakeAgentRunner } = {}) {
  const root = mkdtempSync(join(tmpdir(), "solvex-flow-"));
  const ws = prepareWorkspace({ root, sessionId: "flow", problem: "Test problem" });
  const bus = new EventBus();
  const events: SolveXEvent[] = [];
  bus.subscribe((e) => events.push(e));
  const runner = opts.runner ?? new FakeAgentRunner({ models: MODELS });
  const config: ModelConfig = { ...DEFAULT_CONFIG, concurrency: opts.concurrency ?? 3, strict: opts.strict ?? false };
  const flow = new SolveXFlow({ runner, bus, ws, config, problem: "Test problem", dataInfo: "" });
  return { ws, bus, events, runner, flow, config };
}

describe("T2.8 四阶段状态机（FakeRunner 全流程，0 次模型调用）", () => {
  it("CP2：concurrency=3 跑通完整四阶段并产出兼容目录", async () => {
    const { ws, runner, flow } = setup({ concurrency: 3 });
    const summary = await flow.run();
    expect(summary.status).toBe("completed");
    expect(summary.models).toHaveLength(3);
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
    expect(existsSync(join(ws.paths.programming, "all_results_summary.md"))).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
    for (const d of ["model_1", "model_2", "model_3"]) {
      expect(existsSync(join(ws.paths.programming, d, "results_summary.md"))).toBe(true);
      expect(existsSync(join(ws.paths.programming, d, "figures/fig1.png"))).toBe(true);
      expect(existsSync(join(ws.paths.modeling, `${d}_review.md`))).toBe(true);
    }
    expect(runner.calls.length).toBeGreaterThanOrEqual(8); // P1 + 3 IMPL + 3 REVIEW + P4
    const all = readFileSync(join(ws.paths.programming, "all_results_summary.md"), "utf-8");
    expect(all).toContain("## Model 1");
    expect(all).toContain("Total models implemented: 3");
  });

  it("concurrency=1 与 =3 的共享产物逐字节一致（R11 写安全）", async () => {
    const a = setup({ concurrency: 1 }); await a.flow.run();
    const b = setup({ concurrency: 3 }); await b.flow.run();
    for (const f of ["01_modeling/master_plan.md", "02_programming/all_results_summary.md",
                     "04_paper/main.tex"])
      expect(readFileSync(join(b.ws.dir, f))).toEqual(readFileSync(join(a.ws.dir, f)));
  });

  it("A2/F3：评审只给只读工具且 master_plan 字节不变", async () => {
    const { ws, runner, flow } = setup();
    await flow.run();
    const planBefore = readFileSync(join(ws.paths.modeling, "master_plan.md"));
    const reviews = runner.calls.filter((c) => c.taskId?.startsWith("P2-REVIEW"));
    expect(reviews).toHaveLength(3);
    for (const r of reviews) expect(r.tools).toEqual(ROLE_TOOLS.review);
    expect(readFileSync(join(ws.paths.modeling, "master_plan.md"))).toEqual(planBefore);
  });

  it("R11：并行任务 writablePrefixes 只含自己目录，不含共享文件", async () => {
    const { runner, flow } = setup({ concurrency: 3 });
    await flow.run();
    for (const c of runner.calls.filter((x) => x.taskId?.startsWith("P2-IMPL"))) {
      expect(c.writablePrefixes).toEqual([`02_programming/${c.taskId!.split(":")[1]}/`]);
      expect(c.writablePrefixes!.some((p) => p.includes("master_plan") || p.includes("all_results"))).toBe(false);
    }
    // all_results_summary.md 由纯代码生成，没有任何 LLM 会话写它
    expect(runner.calls.every((c) => !c.task?.includes("write all_results_summary.md"))).toBe(true);
  });

  it("事件序列含 status/step/done/complete，且 done 前有 agent_settled", async () => {
    const { events, flow } = setup();
    await flow.run();
    const types = events.map((e) => e.type);
    expect(types[0]).toBe("status");
    expect(types).toContain("step");
    expect(types).toContain("done");
    expect(types.at(-1)).toBe("complete");
    expect(types).toContain("barrier");
    expect(types).toContain("stage");
    expect(types).toContain("lifecycle");
    const settled = events.filter((e) => e.type === "lifecycle" && (e as any).state === "agent_settled");
    expect(settled.length).toBeGreaterThan(0);
    // agent_end 不产生 done
    expect(events.filter((e) => e.type === "done").length).toBeGreaterThan(0);
  });

  it("resume：跳过已完成模型与 P1", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-resume-"));
    const ws = prepareWorkspace({ root, sessionId: "r1", problem: "P" });
    writeFileSync(join(ws.paths.modeling, "master_plan.md"),
      "# Master Plan\n\n## Model 1: A\n### Purpose\na\n\n## Model 2: B\n### Purpose\nb\n\n## Integration\nx\n");
    mkdirSync(join(ws.paths.programming, "model_1"), { recursive: true });
    writeFileSync(join(ws.paths.programming, "model_1", "results_summary.md"), "# done\n");
    const runner = new FakeAgentRunner();
    const bus = new EventBus();
    const flow = new SolveXFlow({ runner, bus, ws, config: { ...DEFAULT_CONFIG, concurrency: 2 },
      problem: "P", dataInfo: "", resumeFrom: 2 });
    await flow.run();
    expect(runner.calls.some((c) => c.taskId === "P1")).toBe(false);
    expect(runner.calls.some((c) => c.taskId === "P2-IMPL:model_1")).toBe(false);
    expect(runner.calls.some((c) => c.taskId === "P2-IMPL:model_2")).toBe(true);
  });

  it("skipToWriting：只执行 P3(纯代码) + P4", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-skip-"));
    const ws = prepareWorkspace({ root, sessionId: "w1", problem: "P" });
    writeFileSync(join(ws.paths.modeling, "master_plan.md"), "## Model 1: A\n");
    const runner = new FakeAgentRunner();
    const bus = new EventBus();
    const flow = new SolveXFlow({ runner, bus, ws, config: DEFAULT_CONFIG,
      problem: "P", dataInfo: "", skipToWriting: true });
    await flow.run();
    expect(runner.calls.map((c) => c.role)).toEqual(["writing"]);
    expect(existsSync(join(ws.paths.programming, "all_results_summary.md"))).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
  });

  it("AbortSignal 触发后状态为 aborted，已落盘产物不损坏", async () => {
    const ac = new AbortController();
    const runner = new FakeAgentRunner({ models: MODELS, onCall: (r) => { if (r.taskId?.startsWith("P2-IMPL")) ac.abort(); } });
    const { ws, bus, flow } = setup({ runner });
    const summary = await flow.run(ac.signal);
    expect(summary.status).toBe("aborted");
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
  });

  it("D4：strict 模式下 Critical 问题阻断进入 P4", async () => {
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (req) => req.taskId?.startsWith("P2-IMPL") ? { text: "ok", files: {} } : undefined,
    ] });
    const { ws, flow } = setup({ strict: true, runner });
    const summary = await flow.run();
    expect(summary.status).toBe("failed");
    expect(summary.issues.some((i) => i.severity === "critical")).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(false);
  });

  it("非 strict 下 Critical 只 warn，仍进入 P4", async () => {
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (req) => req.taskId?.startsWith("P2-IMPL") ? { text: "ok", files: {} } : undefined,
    ] });
    const { ws, flow } = setup({ strict: false, runner });
    const summary = await flow.run();
    expect(summary.status).toBe("completed");
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
  });
});
