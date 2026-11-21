import { existsSync, readFileSync } from "node:fs";

/**
 * Agent 会话日志 = Pi SDK 自己的 session JSONL（SessionManager 逐条追加，进程崩溃也不丢）。
 * 一个会话可以承载多次调用（例如实现 → 摘要补写 → 各轮评审修复都发进同一个实现会话）。
 * SolveX 只加两种 custom 条目（不进入 LLM 上下文）来划分调用：
 *  - solvex_call   ：某次调用开始（data.call）。
 *  - solvex_result ：该次调用正常结束（data.call），携带最终回复。有它就回放，没有就接着跑。
 */
export const CALL_ENTRY = "solvex_call";
export const RESULT_ENTRY = "solvex_result";

export type JournalUsage = { input: number; output: number; cacheRead: number; cost: number };
export type JournalState = {
  exists: boolean;
  /** 这次调用已经在日志里开始过（有 solvex_call 标记）。 */
  started: boolean;
  /** 这次调用已正常结束（有对应的 solvex_result）。 */
  done?: { text: string; turnCapped?: boolean };
  /** 这次调用已消耗的用量，续跑时接着累加。 */
  usage: JournalUsage;
  /** 这次调用已完成的轮次（assistant 消息数），续跑时轮次预算接着算。 */
  turns: number;
  /** 这次调用的任务已经发出（有 user 消息）：续跑发「继续」，否则发原任务。 */
  prompted: boolean;
  lastText?: string;
  /** 这次调用里提交工具最后一次接受的参数（ADR-0015），回放与续跑时恢复。 */
  submitted?: Record<string, unknown>;
};

/** 提交工具结果的 details 标记：Pi 会把 toolResult 的 details 原样写进 JSONL。 */
export const SUBMIT_DETAILS_KEY = "solvexSubmit";

const zero = (): JournalUsage => ({ input: 0, output: 0, cacheRead: 0, cost: 0 });

function readEntries(path: string): any[] {
  const out: any[] = [];
  for (const line of readFileSync(path, "utf-8").split("\n")) {
    if (!line.trim()) continue;
    try { out.push(JSON.parse(line)); } catch { /* 崩溃时写了半行：跳过，与 Pi 的 loadEntriesFromFile 一致 */ }
  }
  return out;
}

const textOf = (message: any): string => Array.isArray(message?.content)
  ? message.content.filter((c: any) => c?.type === "text").map((c: any) => c.text ?? "").join("")
  : typeof message?.content === "string" ? message.content : "";

/** 与 PiAgentRunner 的实时口径一致：input 含 cacheWrite，cacheRead 单列。 */
export function addUsage(acc: JournalUsage, u: any): void {
  if (!u) return;
  acc.input += (u.input ?? 0) + (u.cacheWrite ?? 0);
  acc.cacheRead += u.cacheRead ?? 0;
  acc.output += u.output ?? 0;
  const c = u.cost;
  acc.cost += typeof c === "number" ? c : (c?.total ?? 0);
}

const isMarker = (e: any, type: string) => e?.type === "custom" && e.customType === type;

/** 读取日志里某一次调用（call）的状态：从它的 solvex_call 标记到下一次调用开始为止。 */
export function inspectJournal(path: string, call: string): JournalState {
  const state: JournalState = { exists: existsSync(path), started: false, usage: zero(), turns: 0, prompted: false };
  if (!state.exists) return state;
  const entries = readEntries(path);
  const start = entries.findIndex((e) => isMarker(e, CALL_ENTRY) && e.data?.call === call);
  if (start < 0) return state;
  state.started = true;
  for (const e of entries.slice(start + 1)) {
    if (isMarker(e, CALL_ENTRY)) break;                       // 下一次调用开始
    if (isMarker(e, RESULT_ENTRY) && e.data?.call === call) {
      state.done = { text: e.data?.text ?? "", ...(e.data?.turnCapped ? { turnCapped: true } : {}) };
      continue;
    }
    if (e?.type !== "message") continue;
    const role = e.message?.role;
    if (role === "user") state.prompted = true;
    const sub = role === "toolResult" ? e.message?.details?.[SUBMIT_DETAILS_KEY] : undefined;
    if (sub?.accepted && sub.args && typeof sub.args === "object") state.submitted = sub.args;
    if (role === "assistant") {
      state.turns++;
      addUsage(state.usage, e.message.usage);
      const t = textOf(e.message);
      if (t) state.lastText = t;
    }
  }
  return state;
}

/** 会话当前的上下文规模：最后一条正常 assistant 消息的 prompt + 输出 token（含缓存命中）。 */
export function lastContextTokens(path: string): number {
  if (!existsSync(path)) return 0;
  const entries = readEntries(path);
  for (let i = entries.length - 1; i >= 0; i--) {
    const m = entries[i]?.type === "message" ? entries[i].message : undefined;
    if (m?.role !== "assistant" || m.stopReason === "error" || m.stopReason === "aborted" || !m.usage) continue;
    const u = m.usage;
    return (u.input ?? 0) + (u.cacheRead ?? 0) + (u.cacheWrite ?? 0) + (u.output ?? 0);
  }
  return 0;
}

export const resumeMessage = (turnsLeft?: number): string =>
  "[SolveX resume] This session was interrupted (the SolveX process stopped) before you finished. " +
  "Everything above — your messages, tool calls and their results — is intact, and the files you wrote " +
  "are still on disk. Continue the original task from where you stopped. Do not start over; if you are " +
  "unsure what was completed, check your output files first." +
  (turnsLeft !== undefined ? ` Only ${turnsLeft} turns remain in this session: save the required ` +
    "deliverables first, then end your turn." : "");
