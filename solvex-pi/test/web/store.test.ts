// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  reduce, createStore, reduceThinkingBlocks, reduceOutputBlocks, truncateThinking,
  utf8ByteLength, MAX_THINKING_BYTES, zeroUsage, emptyTask,
} from "../../apps/web/public/modules/store.js";
import { describe, it, expect } from "vitest";

const ts = () => 1;
const thinking = (o) => ({ type: "thinking", taskId: "P1", blockId: "P1:0", contentIndex: 0, ts: ts(), ...o });
const output = (o) => ({ type: "output", taskId: "P1", blockId: "P1:0", contentIndex: 0, ts: ts(), ...o });
const stage = (o) => ({ type: "stage", op: "upsert", ts: ts(), node: { dependsOn: [], ...o } });

describe("T5.15 store / reduce 纯函数", () => {
  it("createStore 初始结构完整且 reduce 不可变更新", () => {
    const s0 = createStore();
    expect(s0.stages).toEqual({});
    expect(s0.tasks).toEqual({});
    expect(s0.events).toEqual([]);
    expect(s0.usage.global).toEqual(zeroUsage());
    expect(s0.status).toBe("idle");

    const s1 = reduce(s0, stage({ id: "P1", label: "建模", phase: 1, kind: "stage", state: "pending" }));
    expect(s1).not.toBe(s0);                       // 返回新对象
    expect(s0.stages).toEqual({});                // 原对象未被修改
    expect(s0.events).toEqual([]);
    expect(s1.stages.P1.state).toBe("pending");
  });

  it("reduce 对同一 state 重复折叠互不污染（嵌套不可变）", () => {
    const base = reduce(createStore(), thinking({ state: "start" }));
    const a = reduce(base, thinking({ state: "delta", delta: "A" }));
    const b = reduce(base, thinking({ state: "delta", delta: "B" }));
    expect(a.tasks.P1.thinkingBlocks["0"].content).toBe("A");
    expect(b.tasks.P1.thinkingBlocks["0"].content).toBe("B");
    expect(base.tasks.P1.thinkingBlocks["0"].content).toBe("");
  });

  it("thinking_delta 按 contentIndex 追加，thinking_end.content 权威覆盖拼接结果", () => {
    let s = createStore();
    s = reduce(s, thinking({ state: "start" }));
    s = reduce(s, thinking({ state: "delta", delta: "思考" }));
    s = reduce(s, thinking({ state: "delta", delta: "过程" }));
    s = reduce(s, thinking({ state: "delta", delta: "中" }));
    // 拼接结果
    expect(s.tasks.P1.thinkingBlocks["0"].content).toBe("思考过程中");

    // 权威值覆盖（与 delta 拼接不同）
    s = reduce(s, thinking({ state: "end", content: "最终权威思考内容" }));
    const block = s.tasks.P1.thinkingBlocks["0"];
    expect(block.content).toBe("最终权威思考内容");
    expect(block.state).toBe("end");
    expect(block.content).not.toBe("思考过程中");
  });

  it("happy path：thinking_delta 拼接结果 == thinking_end.content", () => {
    let s = createStore();
    s = reduce(s, thinking({ state: "start" }));
    s = reduce(s, thinking({ state: "delta", delta: "A" }));
    s = reduce(s, thinking({ state: "delta", delta: "B" }));
    s = reduce(s, thinking({ state: "delta", delta: "C" }));
    const joined = s.tasks.P1.thinkingBlocks["0"].content;
    expect(joined).toBe("ABC");
    s = reduce(s, thinking({ state: "end", content: "ABC" }));
    expect(s.tasks.P1.thinkingBlocks["0"].content).toBe(joined);
  });

  it("不同 contentIndex 各自成块、互不覆盖", () => {
    let s = createStore();
    s = reduce(s, thinking({ state: "start", contentIndex: 0, blockId: "P1:0" }));
    s = reduce(s, thinking({ state: "delta", contentIndex: 0, delta: "块0" }));
    s = reduce(s, thinking({ state: "start", contentIndex: 1, blockId: "P1:1" }));
    s = reduce(s, thinking({ state: "delta", contentIndex: 1, delta: "块1" }));
    const b = s.tasks.P1.thinkingBlocks;
    expect(Object.keys(b)).toHaveLength(2);
    expect(b["0"].content).toBe("块0");
    expect(b["1"].content).toBe("块1");
  });

  it("thinking_end 携带 redacted 时优雅降级标记", () => {
    let blocks = reduceThinkingBlocks({}, { type: "thinking", state: "start", taskId: "P1", blockId: "P1:0", contentIndex: 0, ts: 1 });
    blocks = reduceThinkingBlocks(blocks, { type: "thinking", state: "end", taskId: "P1", blockId: "P1:0", contentIndex: 0, content: "", redacted: true, ts: 2 });
    expect(blocks["0"].redacted).toBe(true);
    expect(blocks["0"].state).toBe("end");
  });

  it("单块 >64KB 被截断并标记", () => {
    const huge = "汉".repeat(30000); // 约 90KB（UTF-8 三字节）
    expect(utf8ByteLength(huge)).toBeGreaterThan(MAX_THINKING_BYTES);
    const t = truncateThinking(huge);
    expect(t.truncated).toBe(true);
    expect(utf8ByteLength(t.content)).toBeLessThanOrEqual(MAX_THINKING_BYTES);
    // store 也应用同一截断
    let s = reduce(createStore(), thinking({ state: "delta", delta: huge }));
    expect(s.tasks.P1.thinkingBlocks["0"].truncated).toBe(true);
  });

  it("message_end（output state:final）用权威 message 覆盖 partial", () => {
    let s = createStore();
    s = reduce(s, output({ state: "delta", delta: "A" }));
    s = reduce(s, output({ state: "delta", delta: "B" }));
    expect(s.tasks.P1.output["0"].content).toBe("AB"); // partial
    s = reduce(s, output({ state: "final", message: "权威最终消息", content: "权威最终消息" }));
    const b = s.tasks.P1.output["0"];
    expect(b.content).toBe("权威最终消息");
    expect(b.message).toBe("权威最终消息");
    expect(b.state).toBe("final");
    expect(b.authoritative).toBe(true);
  });

  it("output state:end 的 content 覆盖 delta", () => {
    let s = createStore();
    s = reduce(s, output({ state: "delta", delta: "x" }));
    s = reduce(s, output({ state: "delta", delta: "y" }));
    s = reduce(s, output({ state: "delta", delta: "z" }));
    expect(s.tasks.P1.output["0"].content).toBe("xyz");
    s = reduce(s, output({ state: "end", content: "最终输出" }));
    const b = s.tasks.P1.output["0"];
    expect(b.content).toBe("最终输出");
    expect(b.state).toBe("end");
    expect(b.authoritative).toBe(true);
  });

  it("reduceOutputBlocks 直接可用（纯函数）", () => {
    let b = reduceOutputBlocks({}, { type: "output", state: "delta", delta: "临", contentIndex: 3, blockId: "P1:3", taskId: "P1", ts: 1 });
    b = reduceOutputBlocks(b, { type: "output", state: "final", message: "权", content: "权", contentIndex: 3, blockId: "P1:3", taskId: "P1", ts: 2 });
    expect(b["3"].content).toBe("权");
  });

  it("agent_end 绝不把阶段标为 done，也不把 run 标为完成", () => {
    let s = createStore();
    s = reduce(s, stage({ id: "P1", label: "建模", phase: 1, kind: "stage", state: "running" }));
    expect(s.status).toBe("running");

    s = reduce(s, { type: "lifecycle", taskId: "P1", state: "agent_end", ts: 1 });
    expect(s.stages.P1.state).toBe("running");           // 阶段状态不动
    expect(s.status).not.toBe("completed");              // run 未完成

    s = reduce(s, { type: "lifecycle", taskId: "P1", state: "agent_settled", ts: 2 });
    expect(s.stages.P1.state).toBe("running");           // 连 agent_settled 也不改阶段
    expect(s.tasks.P1.lifecycle.map((l) => l.state)).toEqual(["agent_end", "agent_settled"]);

    // 旧版 done 事件同样不完成 run
    const s2 = reduce(createStore(), { type: "done", message: "完成", phase: 1, ts: 1 });
    expect(s2.status).not.toBe("completed");
  });

  it("stage 事件的 node.state 才是阶段权威状态；只有 complete 把 run 标为完成", () => {
    let s = createStore();
    s = reduce(s, stage({ id: "P1", label: "建模", phase: 1, kind: "stage", state: "running" }));
    s = reduce(s, stage({ id: "P1", state: "done" }));   // patch
    expect(s.stages.P1.state).toBe("done");
    expect(s.stages.P1.label).toBe("建模");               // 浅合并保留
    expect(s.status).not.toBe("completed");

    const result = { sessionId: "s", status: "completed", models: [], usageByTask: {}, issues: [], elapsedMs: 10 };
    s = reduce(s, { type: "complete", result, ts: 9 });
    expect(s.status).toBe("completed");
    expect(s.summary).toEqual(result);
  });

  it("stage upsert / remove", () => {
    let s = createStore();
    s = reduce(s, stage({ id: "P2", label: "实现", phase: 2, kind: "task", state: "pending", dependsOn: ["P1"] }));
    expect(Object.keys(s.stages)).toContain("P2");
    s = reduce(s, stage({ id: "P2", state: "running" }));
    expect(s.stages.P2.state).toBe("running");
    s = reduce(s, { type: "stage", op: "remove", ts: 1, node: { id: "P2" } });
    expect(s.stages.P2).toBeUndefined();
  });

  it("barrier 事件更新 3/5 与 released", () => {
    let s = createStore();
    s = reduce(s, { type: "barrier", id: "all-results", state: "waiting", completed: 3, total: 5, ts: 1 });
    expect(s.barriers["all-results"]).toMatchObject({ completed: 3, total: 5, state: "waiting" });
    s = reduce(s, { type: "barrier", id: "all-results", state: "released", completed: 5, total: 5, ts: 2 });
    expect(s.barriers["all-results"].state).toBe("released");
    expect(s.barriers["all-results"].completed).toBe(5);
  });

  it("usage 按任务 + 全局两级累加，全局 == byTask 求和", () => {
    let s = createStore();
    const mk = (taskId, input, output, totalTokens, cost) => ({
      type: "usage", taskId, input, output, cacheRead: 0, cacheWrite: 0, totalTokens, cost, cumulative: false, ts: 1,
    });
    s = reduce(s, mk("P1", 100, 50, 165, 0.5));
    s = reduce(s, mk("P1", 200, 80, 280, 0.7));
    s = reduce(s, mk("P2-IMPL:model_1", 300, 120, 440, 1.2));

    expect(s.usage.byTask["P1"]).toMatchObject({ input: 300, output: 130, totalTokens: 445, cost: 1.2 });
    expect(s.usage.global.input).toBe(600);
    expect(s.usage.global.output).toBe(250);
    expect(s.usage.global.totalTokens).toBe(885);
    expect(s.usage.global.cost).toBeCloseTo(2.4);
    const sum = Object.values(s.usage.byTask).reduce((a, u) => a + u.input, 0);
    expect(s.usage.global.input).toBe(sum);
  });

  it("usage 不重复累加 reasoning（事件里的 reasoning 字段被忽略）", () => {
    let s = createStore();
    s = reduce(s, {
      type: "usage", input: 10, output: 10, cacheRead: 0, cacheWrite: 0,
      totalTokens: 20, cost: 0, reasoning: 9999, cumulative: false, ts: 1,
    });
    expect(s.usage.global.output).toBe(10);
    expect(s.usage.global.totalTokens).toBe(20);
    expect(s.usage.global.reasoning).toBeUndefined();
  });

  it("usage cumulative=true 视为快照覆盖，不重复计数", () => {
    let s = createStore();
    s = reduce(s, { type: "usage", taskId: "P1", input: 100, output: 50, cacheRead: 0, cacheWrite: 0, totalTokens: 150, cost: 0.2, cumulative: false, ts: 1 });
    s = reduce(s, { type: "usage", taskId: "P1", input: 400, output: 200, cacheRead: 0, cacheWrite: 0, totalTokens: 600, cost: 0.9, cumulative: true, ts: 2 });
    expect(s.usage.byTask["P1"].totalTokens).toBe(600);   // 覆盖而非 750
    expect(s.usage.global.totalTokens).toBe(600);
  });

  it("并行 taskId 隔离：thinking / turns / tools / output 不混淆", () => {
    let s = createStore();
    s = reduce(s, thinking({ state: "start", taskId: "A", blockId: "A:0" }));
    s = reduce(s, thinking({ state: "delta", taskId: "A", blockId: "A:0", delta: "AAA" }));
    s = reduce(s, thinking({ state: "start", taskId: "B", blockId: "B:0" }));
    s = reduce(s, thinking({ state: "delta", taskId: "B", blockId: "B:0", delta: "BBB" }));
    s = reduce(s, { type: "turn", taskId: "A", state: "start", turn: 1, ts: 1 });
    s = reduce(s, { type: "tool", taskId: "B", toolCallId: "t1", name: "write", state: "start", ts: 1 });
    s = reduce(s, output({ state: "delta", taskId: "A", blockId: "A:0", delta: "OUT-A" }));

    expect(s.tasks.A.thinkingBlocks["0"].content).toBe("AAA");
    expect(s.tasks.B.thinkingBlocks["0"].content).toBe("BBB");
    expect(s.tasks.A.turns).toHaveLength(1);
    expect(s.tasks.B.turns).toHaveLength(0);
    expect(s.tasks.B.tools.t1.name).toBe("write");
    expect(s.tasks.A.tools.t1).toBeUndefined();
    expect(s.tasks.A.output["0"].content).toBe("OUT-A");
    expect(s.tasks.B.output["0"]).toBeUndefined();
  });

  it("tool 按 toolCallId 归入对应 task，delta 累积 partialResult", () => {
    let s = createStore();
    s = reduce(s, { type: "tool", taskId: "P2", toolCallId: "call1", name: "python", state: "start", ts: 1 });
    s = reduce(s, { type: "tool", taskId: "P2", toolCallId: "call1", name: "python", state: "delta", partialResult: "hel", ts: 2 });
    s = reduce(s, { type: "tool", taskId: "P2", toolCallId: "call1", name: "python", state: "delta", partialResult: "lo", ts: 3 });
    s = reduce(s, { type: "tool", taskId: "P2", toolCallId: "call1", name: "python", state: "end", result: "hello", durationMs: 12, ts: 4 });
    const t = s.tasks.P2.tools.call1;
    expect(t.partial).toBe("hello");
    expect(t.result).toBe("hello");
    expect(t.state).toBe("end");
    expect(t.durationMs).toBe(12);
  });

  it("model 事件刷新顶部条，turn 归入对应 task", () => {
    let s = createStore();
    s = reduce(s, { type: "model", taskId: "P1", provider: "anthropic", model: "claude-x", thinkingLevel: "high", ts: 1 });
    expect(s.model).toMatchObject({ provider: "anthropic", model: "claude-x", thinkingLevel: "high" });
    expect(s.tasks.P1.model.model).toBe("claude-x");
    s = reduce(s, { type: "turn", taskId: "P1", state: "start", turn: 1, ts: 1 });
    s = reduce(s, { type: "turn", taskId: "P1", state: "end", turn: 1, ts: 2 });
    expect(s.tasks.P1.turns.map((t) => t.state)).toEqual(["start", "end"]);
  });

  it("ping 不进 store，events[] 记录其余事件", () => {
    const s0 = createStore();
    expect(reduce(s0, { type: "ping", ts: 1 })).toBe(s0); // 同一引用，不进 store
    let s = reduce(s0, { type: "status", message: "开始", phase: 1, ts: 1 });
    s = reduce(s, { type: "ping", ts: 2 });
    s = reduce(s, { type: "info", message: "信息", phase: 1, ts: 3 });
    expect(s.events.map((e) => e.type)).toEqual(["status", "info"]); // ping 被过滤
  });

  it("error 事件标记 failed", () => {
    const s = reduce(createStore(), { type: "error", message: "boom", ts: 1 });
    expect(s.status).toBe("failed");
    expect(s.error).toBe("boom");
  });

  it("emptyTask 返回全新独立对象", () => {
    const a = emptyTask();
    const b = emptyTask();
    expect(a).not.toBe(b);
    a.turns.push({});
    expect(b.turns).toHaveLength(0);
  });
});
