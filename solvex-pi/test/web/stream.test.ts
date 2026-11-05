// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  parseSseEvent, parseEventData, isPingEvent, applyEvent, replayEvents,
  buildUrls, framesSince, frameId, normalizeStages, normalizeEvents,
  createStore, reduce,
} from "../../apps/web/public/modules/stream.js";
import { describe, it, expect } from "vitest";

describe("T5.16 stream / SSE 续传与 ping 过滤", () => {
  it("parseSseEvent 解析 id / event / data（含多行 data 与注释）", () => {
    const raw = ": heartbeat\nid: 42\nevent: thinking\ndata: {\"type\":\"thinking\",\ndata: \"state\":\"delta\"}\n\n";
    const f = parseSseEvent(raw);
    expect(f).not.toBeNull();
    expect(f.id).toBe("42");            // 自增序号 = Last-Event-ID 续传依据
    expect(f.event).toBe("thinking");
    expect(f.data).toBe("{\"type\":\"thinking\",\n\"state\":\"delta\"}");
  });

  it("parseSseEvent 无 data 返回 null；parseEventData 容错", () => {
    expect(parseSseEvent("id: 7\nevent: ping\n")).toBeNull();
    expect(parseSseEvent(": only comment\n")).toBeNull();
    expect(parseEventData("not-json")).toBeNull();
    expect(parseEventData('{"type":"ping","ts":1}')).toEqual({ type: "ping", ts: 1 });
  });

  it("frameId 从帧字符串取序号", () => {
    expect(frameId("id: 99\nevent: usage\ndata: {}\n")).toBe(99);
    expect(frameId({ id: "12" })).toBe(12);
    expect(frameId("data: {}\n")).toBeNull();
  });

  it("isPingEvent 识别 ping", () => {
    expect(isPingEvent({ type: "ping", ts: 1 })).toBe(true);
    expect(isPingEvent({ type: "status" })).toBe(false);
  });

  it("applyEvent：ping 不进 store（返回同一引用），真实事件进 store", () => {
    const s0 = createStore();
    const same = applyEvent(s0, "id: 5\nevent: ping\ndata: {\"type\":\"ping\",\"ts\":1}\n");
    expect(same).toBe(s0);

    const s1 = applyEvent(s0, {
      type: "stage", op: "upsert", ts: 1,
      node: { id: "P1", label: "建模", phase: 1, kind: "stage", state: "running", dependsOn: [] },
    });
    expect(s1).not.toBe(s0);
    expect(s1.stages.P1.state).toBe("running");
    expect(s1.events).toHaveLength(1);
  });

  it("applyEvent 接受已解析对象与非法数据", () => {
    const s0 = createStore();
    expect(applyEvent(s0, { type: "ping", ts: 1 })).toBe(s0);
    expect(applyEvent(s0, null)).toBe(s0);
    expect(applyEvent(s0, "garbage frame")).toBe(s0);
    const s1 = applyEvent(s0, { type: "barrier", id: "b", state: "waiting", completed: 3, total: 5, ts: 1 });
    expect(s1.barriers.b).toMatchObject({ completed: 3, total: 5 });
  });

  it("replayEvents 按序回放并自动过滤 ping（刷新回放不丢思考/阶段）", () => {
    const frames = [
      { type: "stage", op: "upsert", ts: 1, node: { id: "P1", state: "running", phase: 1 } },
      { type: "thinking", state: "start", taskId: "P1", blockId: "P1:0", contentIndex: 0, ts: 2 },
      { type: "thinking", state: "delta", taskId: "P1", blockId: "P1:0", contentIndex: 0, delta: "思", ts: 3 },
      { type: "thinking", state: "end", taskId: "P1", blockId: "P1:0", contentIndex: 0, content: "权威", ts: 4 },
      { type: "ping", ts: 5 },
      { type: "usage", taskId: "P1", input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: 0.1, cumulative: false, ts: 6 },
    ];
    const s = replayEvents(createStore(), frames);
    expect(s.stages.P1.state).toBe("running");
    expect(s.tasks.P1.thinkingBlocks["0"].content).toBe("权威"); // 权威覆盖
    expect(s.usage.global.totalTokens).toBe(15);
    expect(s.events.map((e) => e.type)).not.toContain("ping");    // ping 被过滤
    expect(s.events).toHaveLength(5);
  });

  it("buildUrls：先拉 events?since=N + stages，再接 stream（续传）", () => {
    const u = buildUrls("http://127.0.0.1:8000", "sess-1", 42);
    expect(u.events).toBe("http://127.0.0.1:8000/api/events/sess-1?since=42");
    expect(u.stages).toBe("http://127.0.0.1:8000/api/stages/sess-1");
    expect(u.stream).toBe("http://127.0.0.1:8000/api/stream/sess-1");
    // since 默认 0；base 尾部斜杠归一化
    expect(buildUrls("", "x").events).toBe("/api/events/x?since=0");
    expect(buildUrls("http://a/", "x", 3).events).toBe("http://a/api/events/x?since=3");
  });

  it("framesSince 按序号过滤，避免续传重复消费", () => {
    const frames = [
      "id: 1\nevent: status\ndata: {}\n",
      "id: 2\nevent: status\ndata: {}\n",
      "id: 3\nevent: status\ndata: {}\n",
    ];
    expect(framesSince(frames, 2)).toHaveLength(1);
    expect(frameId(framesSince(frames, 2)[0])).toBe(3);
  });

  it("normalizeStages / normalizeEvents 兼容多种响应形态", () => {
    expect(normalizeStages([{ id: "P1" }])).toEqual([{ id: "P1" }]);
    expect(normalizeStages({ stages: [{ id: "P2" }] })).toEqual([{ id: "P2" }]);
    expect(normalizeStages({ P1: { id: "P1" }, P2: { id: "P2" } })).toHaveLength(2);
    expect(normalizeEvents({ events: [{ type: "status" }] })).toEqual([{ type: "status" }]);
    expect(normalizeEvents([{ type: "usage" }])).toEqual([{ type: "usage" }]);
  });

  it("stream 模块复用的 reduce 与 store 行为一致", () => {
    const s = reduce(createStore(), { type: "complete", result: { status: "completed" }, ts: 1 });
    expect(s.status).toBe("completed");
  });
});
