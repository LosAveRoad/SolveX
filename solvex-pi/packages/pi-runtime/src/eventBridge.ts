import type { EventBus, SolveXEvent } from "@solvex/core";

export type BridgeContext = { taskId: string; phase?: 1 | 2 | 3 | 4 };
const MAX_BLOCK = 64 * 1024;
const trunc = (s?: string): string | undefined =>
  typeof s === "string" && s.length > MAX_BLOCK ? s.slice(0, MAX_BLOCK) + "\n…[truncated]" : s;

/** 把 Pi Usage 转成 SolveXEvent.usage。
 *  reasoning 是 output 的子集（SDK 官方注释），绝不重复累加；cost 可能是对象。 */
export function usageEvent(u: any, taskId: string, ts: number): SolveXEvent | null {
  if (!u || typeof u !== "object") return null;
  const c = u.cost;
  const cost = typeof c === "number" ? c
    : c && typeof c === "object"
      ? (c.total ?? (c.input ?? 0) + (c.output ?? 0) + (c.cacheRead ?? 0) + (c.cacheWrite ?? 0))
      : 0;
  return {
    type: "usage", taskId,
    input: u.input ?? 0, output: u.output ?? 0,
    cacheRead: u.cacheRead ?? 0, cacheWrite: u.cacheWrite ?? 0,
    totalTokens: u.totalTokens ?? (u.input ?? 0) + (u.output ?? 0),
    cost, cumulative: false, ts,
  };
}

/** 纯函数：Pi AgentSessionEvent / AssistantMessageEvent → SolveXEvent（§4.6 / ADR-12）。
 *  权威值覆盖由前端 store 依据 *_end / message_end 执行，这里保证事件齐备。 */
export function bridgeEvent(raw: any, ctx: BridgeContext, bus: EventBus): void {
  if (!raw || typeof raw !== "object") return;
  const ts = Date.now();
  const taskId = ctx.taskId;
  const bid = (i: number) => `${taskId}:${i}`;
  const emit = (e: SolveXEvent) => bus.emit(e);
  const t = raw.type as string;

  switch (t) {
    case "message_update": {
      const a = raw.assistantMessageEvent;
      if (a && typeof a === "object") {
        const ci = a.contentIndex ?? 0;
        switch (a.type) {
          case "thinking_start":
            emit({ type: "thinking", state: "start", taskId, blockId: bid(ci), contentIndex: ci, ts }); break;
          case "thinking_delta":
            emit({ type: "thinking", state: "delta", taskId, blockId: bid(ci), contentIndex: ci,
                   delta: trunc(a.delta), ts }); break;
          case "thinking_end":
            emit({ type: "thinking", state: "end", taskId, blockId: bid(ci), contentIndex: ci,
                   content: trunc(a.content), redacted: a.redacted, ts }); break;
          case "text_start":
            emit({ type: "output", state: "delta", taskId, blockId: bid(ci), contentIndex: ci, delta: "", ts }); break;
          case "text_delta":
            emit({ type: "output", state: "delta", taskId, blockId: bid(ci), contentIndex: ci,
                   delta: trunc(a.delta), ts }); break;
          case "text_end":
            emit({ type: "output", state: "end", taskId, blockId: bid(ci), contentIndex: ci,
                   content: trunc(a.content), ts }); break;
          case "toolcall_start":
            emit({ type: "tool", taskId, toolCallId: a.id ?? `ci:${ci}`, name: a.toolName ?? "",
                   state: "start", ts }); break;
          case "toolcall_delta":
            emit({ type: "tool", taskId, toolCallId: `ci:${ci}`, name: "", state: "delta",
                   partialResult: trunc(a.delta), ts }); break;
          case "toolcall_end":
            emit({ type: "tool", taskId, toolCallId: a.toolCall?.id ?? `ci:${ci}`,
                   name: a.toolCall?.name ?? "", state: "end", args: a.toolCall?.arguments, ts }); break;
          case "done": case "error": {
            const u = usageEvent(a.usage, taskId, ts); if (u) emit(u);
            break;
          }
        }
      }
      const u2 = usageEvent(raw.message?.usage, taskId, ts); if (u2) emit(u2);
      break;
    }
    case "message_end":
      emit({ type: "output", state: "final", taskId, blockId: bid(0), contentIndex: 0,
             message: raw.message, ts });
      { const u = usageEvent(raw.message?.usage, taskId, ts); if (u) emit(u); }
      break;
    case "tool_execution_start":
      emit({ type: "tool", taskId, toolCallId: raw.toolCallId, name: raw.toolName,
             state: "start", args: raw.args, ts });
      bus.step(`tool: ${raw.toolName}`, (ctx.phase ?? 2) as any, taskId);
      break;
    case "tool_execution_update":
      emit({ type: "tool", taskId, toolCallId: raw.toolCallId, name: raw.toolName,
             state: "update", partialResult: raw.partialResult, ts });
      break;
    case "tool_execution_end":
      emit({ type: "tool", taskId, toolCallId: raw.toolCallId, name: raw.toolName,
             state: "end", result: raw.result, isError: raw.isError, durationMs: raw.durationMs, ts });
      if (raw.isError) bus.warn(`tool ${raw.toolName} failed`, (ctx.phase ?? 2) as any, taskId);
      break;
    case "turn_start": case "turn_end":
      emit({ type: "turn", taskId, state: t === "turn_start" ? "start" : "end", turn: 0, ts });
      break;
    case "agent_start":
      emit({ type: "lifecycle", taskId, state: "agent_start", ts }); break;
    case "agent_end":
      // 只产生 lifecycle，绝不产生 done（ADR-09：自动重试期间会误判）
      emit({ type: "lifecycle", taskId, state: "agent_end",
             ...(raw.willRetry ? { detail: "willRetry" } : {}), ts });
      break;
    case "agent_settled":
      emit({ type: "lifecycle", taskId, state: "agent_settled",
             ...(raw.aborted ? { detail: "aborted" } : {}), ts });
      break;
    case "compaction_start": case "compaction_end":
      emit({ type: "lifecycle", taskId, state: "compaction", detail: t, ts }); break;
    case "auto_retry_start": case "auto_retry_end":
      emit({ type: "lifecycle", taskId, state: "auto_retry", detail: t, ts }); break;
    case "thinking_level_changed":
      emit({ type: "model", taskId, provider: "", model: "", thinkingLevel: raw.level, ts }); break;
    case "bash_execution_update":
      emit({ type: "output", state: "delta", taskId, blockId: bid(0), contentIndex: 0,
             delta: trunc(raw.delta), ts }); break;
  }
}

/** 带节流的状态化桥接器（thinking_delta ≥60ms，R12）。 */
export function createBridge(ctx: BridgeContext, bus: EventBus, minDeltaMs = 60) {
  let last = 0;
  return (raw: any): void => {
    if (raw?.type === "message_update" && raw.assistantMessageEvent?.type === "thinking_delta"
        && Date.now() - last < minDeltaMs) return;
    last = Date.now();
    bridgeEvent(raw, ctx, bus);
  };
}
