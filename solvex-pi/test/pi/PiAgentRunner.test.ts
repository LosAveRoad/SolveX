import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EventBus, ROLE_TOOLS, TOOL_LIST_PLACEHOLDER } from "@solvex/core";
import { PiAgentRunner, compactionPolicy, downgradeThinking } from "@solvex/pi-runtime";
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
  it("安全扩展挂进每个真实 session，并带上本任务的 writablePrefixes 与 cwd（R11 实测回归）", async () => {
    const f = makeFakeSdk();
    const r = req({ writablePrefixes: ["02_programming/model_1/"] });
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(r);
    const factories = f.loaderOptions[0].extensionFactories;
    expect(factories?.length).toBeGreaterThanOrEqual(1);
    let handler: any;
    for (const fac of factories) fac({ on: (e: string, h: any) => { if (e === "tool_call") handler = h; } });
    expect((await handler({ toolName: "write", input: { path: join(r.cwd, "01_modeling/master_plan.md") } })).block).toBe(true);
    expect(await handler({ toolName: "write", input: { path: join(r.cwd, "02_programming/model_1/m.py") } })).toBeUndefined();
  });
  it("usage 每条 assistant 消息只在 message_end 计一次（不随 update/turn_end 重复累加）", async () => {
    const usage = { input: 1000, output: 200, cost: 0 };
    const msg = { role: "assistant", usage };
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_start", message: msg });
      for (let i = 0; i < 5; i++)
        emit({ type: "message_update", message: msg, assistantMessageEvent: { type: "text_delta", delta: "x", contentIndex: 0 } });
      emit({ type: "message_end", message: msg });
      emit({ type: "message_end", message: { role: "toolResult" } });
      emit({ type: "turn_end", message: msg, toolResults: [] });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(r.usage).toEqual({ input: 1000, output: 200, cacheRead: 0, cost: 0 });
  });
  it("重试耗尽后最后一条 assistant 消息为 error → 抛 AgentRunError，不再静默成功", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", stopReason: "error",
        errorMessage: "SSL: UNEXPECTED_EOF_WHILE_READING", usage: { input: 0, output: 0 } } });
    } });
    await expect(new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req()))
      .rejects.toThrow(/AgentRunError\[P2-IMPL:model_1\]: SSL/);
  });
  it("中途出错但重试成功（最后一条是 stop）→ 正常返回", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", stopReason: "error", usage: {} } });
      emit({ type: "message_end", message: { role: "assistant", stopReason: "stop", usage: { input: 5, output: 1 } } });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(r.usage.input).toBe(5);
  });
  it("usage 计入 cacheRead / cacheWrite（与 gateway 实计口径一致）", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", stopReason: "stop",
        usage: { input: 300, cacheRead: 700, cacheWrite: 50, output: 40 } } });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(r.usage).toEqual({ input: 350, cacheRead: 700, output: 40, cost: 0 });
  });
  it("轮次预算：剩 3 轮时 steer 一次；撞上限 abort 但不当作模型故障", async () => {
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      for (let i = 0; i < 10; i++) {
        emit({ type: "message_end", message: { role: "assistant", stopReason: "toolUse", usage: {} } });
        emit({ type: "turn_end", message: {}, toolResults: [] });
      }
      emit({ type: "message_end", message: { role: "assistant", stopReason: "error", usage: {} } });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req({ maxTurns: 10 }));
    expect(f.session.steer).toHaveBeenCalledTimes(1);
    expect(String(f.session.steer.mock.calls[0][0])).toMatch(/Only 3 turns remain/);
    expect(f.session.abort).toHaveBeenCalled();
    expect(r.turnCapped).toBe(true);
  });
  it("重试预算覆盖实测中断窗口：settings 覆盖为 6 次指数退避，并传给 session", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(f.settings.overrides[0].retry).toMatchObject({ enabled: true, maxRetries: 6 });
    expect(f.createOptions[0].settingsManager).toBe(f.settings);
  });
  it("压缩默认沿用 Pi（探针：上下文长度本身不是退化原因）；可选阈值按模型窗口换算 reserveTokens", async () => {
    const glm = { id: "glm", contextWindow: 524288 };
    const rt = { rt: { getModel: () => glm }, resolve: () => glm, scopedModels: () => [] } as any;
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk, modelRuntime: rt }).run(req({ model: { provider: "gw", id: "glm" } }));
    expect(f.settings.overrides[0].compaction).toBeUndefined();
    const g = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: g.sdk, modelRuntime: rt, compactAtTokens: 300_000 })
      .run(req({ model: { provider: "gw", id: "glm" } }));
    expect(g.settings.overrides[0].compaction).toEqual({ enabled: true, reserveTokens: 524288 - 300000, keepRecentTokens: 40000 });
    expect(compactionPolicy(262144, 300_000)).toBeUndefined();                 // 阈值超过窗口：沿用 Pi 默认
    expect(compactionPolicy(524288, Number.POSITIVE_INFINITY)).toBeUndefined();
  });
  it("长上下文 × 最高思考档会退化（探针 177K：max 5/9、high 9/9）：上下文超过 150K 时 xhigh 降到 high", async () => {
    expect(downgradeThinking("xhigh", 177_000)).toBe("high");
    expect(downgradeThinking("xhigh", 126_000)).toBeUndefined();
    expect(downgradeThinking("high", 300_000)).toBeUndefined();
    // 会话中途越过阈值：切一次
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", content: [], stopReason: "toolUse",
        usage: { input: 2000, cacheRead: 120_000, output: 500 } } });
      emit({ type: "message_end", message: { role: "assistant", content: [], stopReason: "toolUse",
        usage: { input: 3000, cacheRead: 160_000, output: 500 } } });
      emit({ type: "message_end", message: { role: "assistant", content: [], stopReason: "stop",
        usage: { input: 1000, cacheRead: 170_000, output: 500 } } });
      emit({ type: "agent_settled", aborted: false });
    } });
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req({ thinkingLevel: "xhigh" }));
    expect(f.createOptions[0].thinkingLevel).toBe("xhigh");
    expect(f.session.setThinkingLevel).toHaveBeenCalledTimes(1);
    expect(f.session.setThinkingLevel).toHaveBeenCalledWith("high");
  });
  it("发进已有长会话的新调用（评审修复发进 175K 的实现会话）一开始就用 high", async () => {
    const dir = mkdtempSync(join(tmpdir(), "solvex-dg-"));
    const path = join(dir, ".solvex/journal/P2-IMPL_model_3.jsonl");
    mkdirSync(join(dir, ".solvex/journal"), { recursive: true });
    writeFileSync(path, [
      { type: "session", version: 3, id: "s", cwd: dir },
      { type: "custom", customType: "solvex_call", data: { call: "impl" } },
      { type: "message", message: { role: "assistant", content: [], stopReason: "stop", usage: { input: 1000, cacheRead: 174_000, output: 300 } } },
      { type: "custom", customType: "solvex_result", data: { call: "impl", text: "done" } },
    ].map((e) => JSON.stringify(e)).join("\n") + "\n");
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req({ cwd: dir, thinkingLevel: "xhigh",
      journal: { path, call: "fix-1" } }));
    expect(f.createOptions[0].thinkingLevel).toBe("high");
    expect(f.session.setThinkingLevel).not.toHaveBeenCalled();
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

describe("断点续跑：会话日志就是 Pi 的 JSONL", () => {
  const lines = (p: string) => readFileSync(p, "utf-8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const assistant = (text: string, usage: any = { input: 10, output: 5, cacheRead: 20 }) =>
    ({ role: "assistant", stopReason: "stop", usage, content: [{ type: "text", text }] });
  const oneTurn = (text: string, usage?: any) => async (emit: (e: any) => void) => {
    emit({ type: "message_end", message: assistant(text, usage) });
    emit({ type: "turn_end", message: {}, toolResults: [] });
    emit({ type: "agent_settled", aborted: false });
  };
  const jreq = (dir: string, over: any = {}) =>
    req({ cwd: dir, journal: { path: join(dir, ".solvex/journal/P2-IMPL_model_1.jsonl"), call: "impl" }, ...over });
  const writeJournal = (p: string, entries: any[], call = "impl") => {
    mkdirSync(join(p, ".."), { recursive: true });
    writeFileSync(p, [{ type: "session", version: 3, id: "s", cwd: "/x" },
      { type: "custom", customType: "solvex_call", data: { call } }, ...entries]
      .map((e, i) => JSON.stringify({ id: `e${i}`, ...e })).join("\n") + "\n");
  };

  it("首次运行：日志落在指定路径，正常结束写入完成标记", async () => {
    const dir = cwd();
    const f = makeFakeSdk({ promptImpl: oneTurn("done-1") });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(jreq(dir));
    const p = jreq(dir).journal.path;
    expect((f.sdk.SessionManager as any).open).toHaveBeenCalledWith(p, join(dir, ".solvex/journal"), dir);
    const es = lines(p);
    expect(es.some((e) => e.type === "message" && e.message.role === "user" && e.message.content === "TASK")).toBe(true);
    expect(es.find((e) => e.customType === "solvex_call")).toMatchObject({ data: { call: "impl" } });
    expect(es.at(-1)).toMatchObject({ type: "custom", customType: "solvex_result", data: { call: "impl", text: "final answer" } });
    expect(r.replayed).toBeUndefined();
  });

  it("已完成的调用直接回放：不建会话、不调用模型，用量取自日志", async () => {
    const dir = cwd();
    await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk({ promptImpl: oneTurn("x") }).sdk }).run(jreq(dir));
    const f2 = makeFakeSdk();
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f2.sdk }).run(jreq(dir));
    expect(f2.sdk.createAgentSession).not.toHaveBeenCalled();
    expect(r).toMatchObject({ replayed: true, text: "final answer", usage: { input: 10, output: 5, cacheRead: 20 } });
  });

  it("中断的调用从日志接着跑：发「继续」而不是原任务，轮次与用量接着累加", async () => {
    const dir = cwd();
    const p = jreq(dir).journal.path;
    writeJournal(p, [
      { type: "message", message: { role: "user", content: "TASK" } },
      ...Array.from({ length: 10 }, () => ({ type: "message", message: assistant("step", { input: 1, output: 1 }) })),
    ]);
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      for (let i = 0; i < 3; i++) {
        emit({ type: "message_end", message: assistant("more", { input: 2, output: 2 }) });
        emit({ type: "turn_end", message: {}, toolResults: [] });
      }
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(jreq(dir, { maxTurns: 15 }));
    const sent = String(f.session.prompt.mock.calls[0][0]);
    expect(sent).toMatch(/\[SolveX resume\]/);
    expect(sent).not.toBe("TASK");
    expect(r.resumed).toBe(true);
    expect(r.usage).toMatchObject({ input: 16, output: 16 });       // 10×1 + 3×2
    // 第 12 轮（15 - 3）时提醒预算：轮次是从日志里的 10 轮接着数的
    expect(f.session.steer).toHaveBeenCalledTimes(1);
    expect(String(f.session.steer.mock.calls[0][0])).toMatch(/Only 3 turns remain/);
  });

  it("出错的调用不写完成标记，下次接着跑", async () => {
    const dir = cwd();
    const f = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", stopReason: "error", errorMessage: "TLS", usage: {} } });
    } });
    await expect(new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(jreq(dir))).rejects.toThrow(/TLS/);
    expect(lines(jreq(dir).journal.path).some((e) => e.customType === "solvex_result")).toBe(false);
    const f2 = makeFakeSdk({ promptImpl: oneTurn("ok") });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f2.sdk }).run(jreq(dir));
    expect(r.resumed).toBe(true);
  });

  it("同一会话多次调用：新调用接在会话末尾（继承上下文）、发原任务，回放与用量按调用区分", async () => {
    const dir = cwd();
    const path = join(dir, ".solvex/journal/P2-IMPL_model_1.jsonl");
    await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk({ promptImpl: oneTurn("impl") }).sdk }).run(jreq(dir));
    // 评审修复意见发进同一个实现会话
    const f = makeFakeSdk({ promptImpl: oneTurn("fixed", { input: 3, output: 1 }) });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk })
      .run(req({ cwd: dir, task: "FIX IT", journal: { path, call: "fix-1" } }));
    expect(String(f.session.prompt.mock.calls[0][0])).toBe("FIX IT");
    expect(r.resumed).toBeUndefined();
    expect(r.usage).toMatchObject({ input: 3, output: 1, cacheRead: 0 });   // 不含 impl 调用的用量
    const es = lines(path);
    const iImpl = es.findIndex((e) => e.message?.content === "TASK");
    const iFix = es.findIndex((e) => e.message?.content === "FIX IT");
    expect(iImpl).toBeGreaterThan(0);
    expect(iFix).toBeGreaterThan(iImpl);                                   // 同一文件、接在后面
    expect(es.filter((e) => e.customType === "solvex_result").map((e) => e.data.call)).toEqual(["impl", "fix-1"]);
    // 两次调用分别回放，互不混淆
    const a = await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk().sdk }).run(jreq(dir));
    const b = await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk().sdk })
      .run(req({ cwd: dir, task: "FIX IT", journal: { path, call: "fix-1" } }));
    expect(a).toMatchObject({ replayed: true, usage: { input: 10, output: 5, cacheRead: 20 } });
    expect(b).toMatchObject({ replayed: true, usage: { input: 3, output: 1 } });
  });

  it("后一次调用中断：只续它自己，前一次调用照常回放", async () => {
    const dir = cwd();
    const path = join(dir, ".solvex/journal/P2-IMPL_model_1.jsonl");
    await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk({ promptImpl: oneTurn("impl") }).sdk }).run(jreq(dir));
    const crash = makeFakeSdk({ promptImpl: async (emit) => {
      emit({ type: "message_end", message: { role: "assistant", stopReason: "error", errorMessage: "killed", usage: {} } });
    } });
    await expect(new PiAgentRunner({ bus: new EventBus(), sdk: crash.sdk })
      .run(req({ cwd: dir, task: "FIX IT", journal: { path, call: "fix-1" } }))).rejects.toThrow(/killed/);
    const f = makeFakeSdk({ promptImpl: oneTurn("ok") });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk })
      .run(req({ cwd: dir, task: "FIX IT", journal: { path, call: "fix-1" } }));
    expect(r.resumed).toBe(true);
    expect(String(f.session.prompt.mock.calls[0][0])).toMatch(/\[SolveX resume\]/);
    expect(lines(path).filter((e) => e.customType === "solvex_call").length).toBe(2);   // 不重复写开始标记
    const impl = await new PiAgentRunner({ bus: new EventBus(), sdk: makeFakeSdk().sdk }).run(jreq(dir));
    expect(impl.replayed).toBe(true);
  });

  it("撞上限后、写标记前进程退出：直接补记截断结束，不再调用模型", async () => {
    const dir = cwd();
    const p = jreq(dir).journal.path;
    writeJournal(p, [
      { type: "message", message: { role: "user", content: "TASK" } },
      ...Array.from({ length: 5 }, (_, i) => ({ type: "message", message: assistant(`s${i}`) })),
    ]);
    const f = makeFakeSdk();
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(jreq(dir, { maxTurns: 5 }));
    expect(f.sdk.createAgentSession).not.toHaveBeenCalled();
    expect(r).toMatchObject({ turnCapped: true, text: "s4" });
  });
});

describe("提交工具（ADR-0015）：注册进会话，接受的提交随日志回放", () => {
  const sub = (log: any[]) => ({
    name: "submit_review", description: "Submit your finished review.",
    parameters: { type: "object" as const, properties: { verdict: { type: "string" } }, required: ["verdict"] },
    check: (a: any) => { log.push(a); return a.verdict === "SATISFIED" ? null : "verdict must be SATISFIED"; },
  });

  it("工具进 tools / customTools / 提示词；拒绝时把原因作为工具错误回给模型，接受后 RunResult 带参数；回放从日志恢复", async () => {
    const dir = cwd();
    const path = join(dir, ".solvex/journal/P2-REVIEW_model_1.review-1.jsonl");
    const log: any[] = [];
    let results: any[] = [];
    let f: any;
    f = makeFakeSdk({ promptImpl: async (emit) => {
      const tool = f.createOptions[0].customTools.find((t: any) => t.name === "submit_review");
      for (const verdict of ["maybe", "SATISFIED"]) {
        const r = await tool.execute("id", { verdict });
        results.push(r);
        emit({ type: "message_end", message: { role: "toolResult", toolName: "submit_review", content: r.content,
                                               details: r.details, isError: !!r.isError } });
      }
      emit({ type: "message_end", message: { role: "assistant", stopReason: "stop", usage: {}, content: [{ type: "text", text: "ok" }] } });
      emit({ type: "agent_settled", aborted: false });
    } });
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk })
      .run(req({ cwd: dir, role: "review", tools: ROLE_TOOLS.review, systemPrompt: `SYS\n${TOOL_LIST_PLACEHOLDER}`,
                 submit: sub(log), journal: { path, call: "review" } }));
    expect(f.createOptions[0].tools).toContain("submit_review");
    expect(f.loaderOptions[0].systemPromptOverride()).toContain("submit_review: Submit your finished review.");
    expect(results[0]).toMatchObject({ isError: true });
    expect(results[0].content[0].text).toMatch(/Submission rejected:\nverdict must be SATISFIED/);
    expect(results[1].isError).toBeUndefined();
    expect(r.submitted).toEqual({ verdict: "SATISFIED" });
    expect(log).toHaveLength(2);

    const f2 = makeFakeSdk();
    const again = await new PiAgentRunner({ bus: new EventBus(), sdk: f2.sdk })
      .run(req({ cwd: dir, role: "review", submit: sub(log), journal: { path, call: "review" } }));
    expect(f2.sdk.createAgentSession).not.toHaveBeenCalled();
    expect(again).toMatchObject({ replayed: true, submitted: { verdict: "SATISFIED" } });
  });

  it("没有提交工具的调用不注册任何额外工具；没调用提交工具 → submitted 缺省", async () => {
    const f = makeFakeSdk();
    const r = await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run(req());
    expect(f.createOptions[0].tools).not.toContain("submit_review");
    expect(r.submitted).toBeUndefined();
  });

  it("check 抛异常：按拒绝处理，不让会话崩掉", async () => {
    const { submitCustomTool } = await import("@solvex/pi-runtime");
    const t = submitCustomTool({ name: "submit_fix", description: "d", parameters: { type: "object", properties: {} },
      check: () => { throw new Error("disk full"); } }, () => { throw new Error("must not accept"); });
    const out = await t.execute("id", {});
    expect(out.isError).toBe(true);
    expect(out.content[0].text).toContain("disk full");
  });
});
