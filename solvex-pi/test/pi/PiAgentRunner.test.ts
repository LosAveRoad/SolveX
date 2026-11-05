import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EventBus, ROLE_TOOLS } from "@solvex/core";
import { PiAgentRunner } from "@solvex/pi-runtime";
import { makeFakeSdk } from "./fakeSdk.js";

const cwd = () => mkdtempSync(join(tmpdir(), "solvex-pi-"));
const req = (over: any = {}) => ({ role: "programming", systemPrompt: "SYS", task: "TASK",
  cwd: cwd(), taskId: "P2-IMPL:model_1", phase: 2 as const, tools: ROLE_TOOLS.programming, ...over });

describe("T3.2 PiAgentRunner（mock SDK）", () => {
  it("① systemPromptOverride 生效；② appendSystemPromptOverride 返回 []", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(f.loaderOptions[0].systemPromptOverride()).toBe("SYS");
    expect(f.loaderOptions[0].appendSystemPromptOverride()).toEqual([]);
  });
  it("③ tools 白名单按角色；④ sessionManager 为 inMemory", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(f.createOptions[0].tools).toEqual(ROLE_TOOLS.programming);
    expect(f.createOptions[0].sessionManager).toEqual({ kind: "inMemory" });
    expect((f.sdk.SessionManager as any).inMemory).toHaveBeenCalled();
  });
  it("⑤ finally 中 unsubscribe + dispose 必然执行（含抛错路径）", async () => {
    const f = makeFakeSdk({ promptImpl: async () => { throw new Error("prompt failed"); } });
    await expect(new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req())).rejects.toThrow("prompt failed");
    expect(f.unsubscribe).toHaveBeenCalledTimes(1);
    expect(f.session.dispose).toHaveBeenCalledTimes(1);
  });
  it("⑥ AbortSignal → session.abort() + waitForIdle()", async () => {
    const f = makeFakeSdk(); const ac = new AbortController(); ac.abort();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req(), ac.signal);
    expect(f.session.abort).toHaveBeenCalled();
    expect(f.session.waitForIdle).toHaveBeenCalled();
  });
  it("⑦ model/thinkingLevel/scopedModels/modelRuntime 按 RunRequest 传入", async () => {
    const f = makeFakeSdk();
    const rt = { rt: { getModel: () => ({ id: "m" }) }, resolve: () => ({ id: "m" }),
      scopedModels: (ids: string[]) => ids.map((model) => ({ model })) } as any;
    const runner = new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk, modelRuntime: rt });
    await runner.run(req({ model: { provider: "anthropic", id: "claude" },
      thinkingLevel: "high", scopedModels: ["a/b", "c/d"] }));
    expect(f.createOptions[0].model).toEqual({ id: "m" });
    expect(f.createOptions[0].thinkingLevel).toBe("high");
    expect(f.createOptions[0].scopedModels).toHaveLength(2);
    expect(f.createOptions[0].modelRuntime).toBe(rt.rt);
  });
  it("⑧ taskId 透传给事件桥接，事件带正确 taskId", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_update", message: {}, assistantMessageEvent:
        { type: "thinking_start", contentIndex: 0 } });
    } });
    const bus = new EventBus(); const types: string[] = [];
    bus.subscribe((e) => types.push(e.type));
    await new PiAgentRunner({ bus, sdk: f.sdk }).run(req());
    const thinking = bus.history().map((r) => r.event).find((e) => e.type === "thinking") as any;
    expect(thinking.taskId).toBe("P2-IMPL:model_1");
  });
  it("getLastAssistantText 与 settled 语义：只认 agent_settled", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "agent_end", messages: [], willRetry: false });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(r.text).toBe("final answer");
    expect(r.settled).toBe(false); // 只有 agent_end，没有 settled
  });
});
