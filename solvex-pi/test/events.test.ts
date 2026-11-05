import { describe, it, expect } from "vitest";
import {
  THINKING_LEVELS, SOLVEX_EVENT_TYPES, type SolveXEvent, type StageNode, type RunSummary,
} from "@solvex/core";

describe("SolveXEvent v1.1 契约", () => {
  it("7 档 thinking level 且事件类型覆盖 12 类", () => {
    expect(THINKING_LEVELS).toEqual(["off", "minimal", "low", "medium", "high", "xhigh", "max"]);
    for (const t of ["status", "step", "done", "info", "warn", "artifact", "complete", "error",
                     "stage", "barrier", "thinking", "output", "tool", "turn", "model", "usage",
                     "lifecycle", "ping"]) expect(SOLVEX_EVENT_TYPES).toContain(t);
  });

  it("事件联合可穷尽（编译期 + 运行期判别）", () => {
    const ev: SolveXEvent = { type: "thinking", state: "delta", taskId: "P2-IMPL:model_1",
      blockId: "P2-IMPL:model_1:0", contentIndex: 0, delta: "考虑拉格朗日松弛", ts: 1 };
    expect(ev.type).toBe("thinking");
    const node: StageNode = { id: "P1", label: "Master Plan", phase: 1, kind: "stage",
      state: "running", dependsOn: [] };
    expect(node.state).toBe("running");
    const sum: RunSummary = { sessionId: "s1", models: [], usageByTask: {}, issues: [],
      elapsedMs: 0, status: "running" };
    expect(sum.status).toBe("running");
  });
});
