import { describe, it, expect } from "vitest";
import { EventBus, type RunSummary } from "@solvex/core";

const summary: RunSummary = { sessionId: "s", status: "completed", models: [],
  usageByTask: {}, issues: [], elapsedMs: 1 };

describe("T2.7 EventBus", () => {
  it("emit 同步通知订阅者", () => {
    const bus = new EventBus(); const got: string[] = [];
    bus.subscribe((e) => got.push(e.type));
    bus.status("hi", 1);
    expect(got).toEqual(["status"]);
  });
  it("history(since) 可回放且订阅可取消", () => {
    const bus = new EventBus();
    bus.status("a", 1); bus.step("b", 2); bus.done("c", 3);
    expect(bus.history(1).map((r) => r.event.type)).toEqual(["step", "done"]);
    const off = bus.subscribe(() => { throw new Error("should not fire"); });
    off(); bus.info("d", 1);
  });
  it("complete / error 标记终态", () => {
    const a = new EventBus(); a.complete(summary); expect(a.state).toBe("complete");
    const b = new EventBus(); b.error("boom", 2); expect(b.state).toBe("error");
    expect(b.history()[0].event.type).toBe("error");
  });
  it("stage / barrier / lifecycle 事件结构正确", () => {
    const bus = new EventBus(); const types: string[] = [];
    bus.subscribe((e) => types.push(e.type));
    bus.stage({ id: "P1", label: "P1", phase: 1, kind: "stage", state: "running", dependsOn: [] });
    bus.barrier("b", "waiting", 2, 5);
    bus.lifecycle("P1", "agent_settled");
    expect(types).toEqual(["stage", "barrier", "lifecycle"]);
  });
});
