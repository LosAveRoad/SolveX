// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  isRedacted, defaultCollapsed, toggleFold, blockSummary, groupThinkingByTask,
  applyThinkingEvent, truncateThinking, utf8ByteLength, MAX_THINKING_BYTES,
} from "../../apps/web/public/modules/thinking.js";
import { describe, it, expect } from "vitest";

const ev = (o) => ({ type: "thinking", taskId: "P1", blockId: "P1:0", contentIndex: 0, ts: 1, ...o });

describe("T5.18 thinking 思考过程视图（折叠 / redacted / 64KB / contentIndex）", () => {
  it("默认折叠 + toggleFold 切换", () => {
    expect(defaultCollapsed()).toBe(true);
    expect(toggleFold(true)).toBe(false);
    expect(toggleFold(false)).toBe(true);
  });

  it("blockSummary 摘要行显示字数与耗时", () => {
    const block = { content: "一二三四五", charCount: 5, startedAt: 1000, endedAt: 13400, redacted: false };
    const sum = blockSummary(block);
    expect(sum.text).toContain("思考");
    expect(sum.text).toContain("12.4s");
    expect(sum.text).toContain("5 字");
    expect(sum.text).toContain("点击展开");
    expect(sum.durationMs).toBe(12400);
    expect(sum.chars).toBe(5);
  });

  it("blockSummary 未结束块显示「计算中」", () => {
    const sum = blockSummary({ content: "abc", charCount: 3, startedAt: 1000, endedAt: null });
    expect(sum.text).toContain("计算中");
  });

  it("redacted 块优雅降级：摘要显示不可见、不报错", () => {
    const block = { content: "", charCount: 0, redacted: true, startedAt: 1, endedAt: 2 };
    expect(isRedacted(block)).toBe(true);
    const sum = blockSummary(block);
    expect(sum.redacted).toBe(true);
    expect(sum.text).toContain("该模型的思考内容不可见");
  });

  it("thinking_end 带 redacted 时标记降级", () => {
    let blocks = applyThinkingEvent({}, ev({ state: "start" }));
    blocks = applyThinkingEvent(blocks, ev({ state: "end", content: "", redacted: true, ts: 2 }));
    expect(isRedacted(blocks["0"])).toBe(true);
    expect(blocks["0"].state).toBe("end");
  });

  it("单块 >64KB 按 UTF-8 字节截断并标记", () => {
    const huge = "汉".repeat(30000); // ~90KB
    expect(utf8ByteLength(huge)).toBeGreaterThan(MAX_THINKING_BYTES);
    const t = truncateThinking(huge);
    expect(t.truncated).toBe(true);
    expect(utf8ByteLength(t.content)).toBeLessThanOrEqual(MAX_THINKING_BYTES);
    expect(t.content.length).toBeLessThan(huge.length);
    // 未超限不截断
    const small = truncateThinking("短文本");
    expect(small.truncated).toBe(false);
    expect(small.content).toBe("短文本");
  });

  it("按 contentIndex 追加：同块 delta 拼接，不同块隔离", () => {
    let blocks = applyThinkingEvent({}, ev({ state: "start", contentIndex: 0, blockId: "P1:0" }));
    blocks = applyThinkingEvent(blocks, ev({ state: "delta", contentIndex: 0, delta: "A" }));
    blocks = applyThinkingEvent(blocks, ev({ state: "delta", contentIndex: 0, delta: "B" }));
    blocks = applyThinkingEvent(blocks, ev({ state: "start", contentIndex: 1, blockId: "P1:1" }));
    blocks = applyThinkingEvent(blocks, ev({ state: "delta", contentIndex: 1, delta: "C" }));
    expect(blocks["0"].content).toBe("AB");
    expect(blocks["1"].content).toBe("C");
    // end 权威覆盖
    blocks = applyThinkingEvent(blocks, ev({ state: "end", contentIndex: 0, content: "权威" }));
    expect(blocks["0"].content).toBe("权威");
    expect(blocks["1"].content).toBe("C"); // 另一块不受影响
  });

  it("groupThinkingByTask 并行任务分栏不混淆", () => {
    const state = {
      tasks: {
        A: { thinkingBlocks: { 0: { content: "AAA" } } },
        B: { thinkingBlocks: { 0: { content: "BBB" }, 1: { content: "BBB2" } } },
        C: { thinkingBlocks: {} },
      },
    };
    const grouped = groupThinkingByTask(state);
    expect(Object.keys(grouped)).toEqual(["A", "B"]); // 空块任务不出现
    expect(grouped.A).toHaveLength(1);
    expect(grouped.B).toHaveLength(2);
    expect(grouped.B[0].content).toContain("BBB");
  });
});
