import { describe, it, expect } from "vitest";
import { renderEvent } from "../../apps/cli/src/renderer.js";

describe("T4.2 CLI 彩色渲染", () => {
  it("status/step/done/info/warn 各自格式", () => {
    const ev = (type: any) => ({ type, message: "M", phase: 1, ts: 0 });
    expect(renderEvent(ev("status"))).toContain("=".repeat(50));
    expect(renderEvent(ev("step"))).toContain(">>> M");
    expect(renderEvent(ev("done"))).toContain("✓ M");
    expect(renderEvent(ev("warn"))).toContain("⚠ M");
    expect(renderEvent(ev("info"))).toBe("  M");
  });
  it("新增结构化事件降级为不刷屏（usage/ping 返回 undefined）", () => {
    expect(renderEvent({ type: "usage", taskId: "T", input: 1, output: 2, cacheRead: 0,
      cacheWrite: 0, totalTokens: 3, cost: 0, cumulative: false, ts: 0 })).toBeUndefined();
    expect(renderEvent({ type: "ping", ts: 0 })).toBeUndefined();
  });
  it("complete 汇总状态/模型/token/耗时", () => {
    const s = renderEvent({ type: "complete", result: { sessionId: "s", status: "completed",
      models: [{ name: "Model 1", dir: "model_1", verdict: "satisfied", issues: [] }],
      usageByTask: {}, issues: [], elapsedMs: 1200, totalTokens: 500 }, ts: 0 });
    expect(s).toContain("completed");
    expect(s).toContain("token=500");
  });
});
