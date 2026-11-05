import { describe, it, expect } from "vitest";
import { EventBus, type SolveXEvent } from "@solvex/core";
import { bridgeEvent, usageEvent, createBridge } from "@solvex/pi-runtime";

const collect = () => {
  const bus = new EventBus(); const got: SolveXEvent[] = [];
  bus.subscribe((e) => got.push(e));
  return { bus, got };
};
const msg = (a: any) => ({ type: "message_update", message: {}, assistantMessageEvent: a });

describe("T3.4/T3.7 eventBridge（ADR-12）", () => {
  it("thinking_start/_delta/_end 按 contentIndex 关联，end 带权威 content", () => {
    const { bus, got } = collect();
    for (const a of [
      { type: "thinking_start", contentIndex: 0 },
      { type: "thinking_delta", contentIndex: 0, delta: "考虑" },
      { type: "thinking_delta", contentIndex: 0, delta: "拉格朗日松弛" },
      { type: "thinking_end", contentIndex: 0, content: "考虑拉格朗日松弛" },
    ]) bridgeEvent(msg(a), { taskId: "P2-IMPL:model_1" }, bus);
    const th = got.filter((e) => e.type === "thinking") as any[];
    expect(th.map((e) => e.state)).toEqual(["start", "delta", "delta", "end"]);
    expect(th.every((e) => e.blockId === "P2-IMPL:model_1:0")).toBe(true);
    expect(th.filter((e) => e.state === "delta").map((e) => e.delta).join(""))
      .toBe(th.find((e) => e.state === "end").content);
  });
  it("text_* → output(delta/end)，message_end → output(final)", () => {
    const { bus, got } = collect();
    bridgeEvent(msg({ type: "text_delta", contentIndex: 1, delta: "hi" }), { taskId: "T" }, bus);
    bridgeEvent(msg({ type: "text_end", contentIndex: 1, content: "hi" }), { taskId: "T" }, bus);
    bridgeEvent({ type: "message_end", message: { usage: { input: 1, output: 2 } } }, { taskId: "T" }, bus);
    expect(got.filter((e) => e.type === "output").map((e) => (e as any).state))
      .toEqual(["delta", "end", "final"]);
  });
  it("tool_execution_* → tool + step；isError → warn", () => {
    const { bus, got } = collect();
    bridgeEvent({ type: "tool_execution_start", toolCallId: "c1", toolName: "bash", args: {} }, { taskId: "T", phase: 2 }, bus);
    bridgeEvent({ type: "tool_execution_end", toolCallId: "c1", toolName: "bash", result: "ok", isError: false }, { taskId: "T", phase: 2 }, bus);
    bridgeEvent({ type: "tool_execution_end", toolCallId: "c2", toolName: "python_execute", result: "boom", isError: true }, { taskId: "T", phase: 2 }, bus);
    expect(got.filter((e) => e.type === "tool")).toHaveLength(3);
    expect(got.filter((e) => e.type === "step")).toHaveLength(1);
    expect(got.filter((e) => e.type === "warn")).toHaveLength(1);
  });
  it("agent_end 不产生 done；只有 agent_settled 才标记结束", () => {
    const { bus, got } = collect();
    bridgeEvent({ type: "agent_end", messages: [], willRetry: true }, { taskId: "T" }, bus);
    expect(got.some((e) => e.type === "done")).toBe(false);
    expect(got.find((e) => e.type === "lifecycle")).toMatchObject({ state: "agent_end", detail: "willRetry" });
    bridgeEvent({ type: "agent_settled", aborted: false }, { taskId: "T" }, bus);
    expect(got.filter((e) => e.type === "lifecycle").map((e) => (e as any).state))
      .toEqual(["agent_end", "agent_settled"]);
  });
  it("usage.reasoning 是 output 子集，绝不重复累加", () => {
    const u = usageEvent({ input: 100, output: 1000, reasoning: 400, cacheRead: 10, cacheWrite: 5,
      totalTokens: 1115, cost: { input: 1, output: 2, cacheRead: 0, cacheWrite: 0, total: 3 } }, "T", 1);
    expect(u).toMatchObject({ output: 1000, totalTokens: 1115, cost: 3 });
    expect((u as any).reasoning).toBeUndefined();
  });
  it("thinking_level_changed → model；compaction/auto_retry → lifecycle", () => {
    const { bus, got } = collect();
    bridgeEvent({ type: "thinking_level_changed", level: "high" }, { taskId: "T" }, bus);
    bridgeEvent({ type: "compaction_start", reason: "threshold" }, { taskId: "T" }, bus);
    bridgeEvent({ type: "auto_retry_start", attempt: 1, maxAttempts: 3, delayMs: 1000, errorMessage: "429" }, { taskId: "T" }, bus);
    expect(got.find((e) => e.type === "model")).toMatchObject({ thinkingLevel: "high" });
    expect(got.filter((e) => e.type === "lifecycle")).toHaveLength(2);
  });
  it("单块 >64KB 截断标记 + thinking_delta 节流", () => {
    const { bus, got } = collect();
    bridgeEvent(msg({ type: "thinking_end", contentIndex: 0, content: "x".repeat(70000) }), { taskId: "T" }, bus);
    expect((got[0] as any).content).toContain("[truncated]");
    const bridge = createBridge({ taskId: "T" }, bus, 1000);
    bridge(msg({ type: "thinking_delta", contentIndex: 0, delta: "a" }));
    bridge(msg({ type: "thinking_delta", contentIndex: 0, delta: "b" }));
    expect(got.filter((e) => e.type === "thinking" && (e as any).state === "delta")).toHaveLength(1);
  });
});
