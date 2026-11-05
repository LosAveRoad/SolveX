/* SolveX WebUI 2.0 —— 单一会话状态容器（无构建链，原生 ESM）。
 * 核心是纯函数 reduce(state, event)：每次返回【全新】state 对象，绝不原地修改入参。
 * 事件契约见设计文档 §4.6 / types.ts；流式重建三原则见 §10.4。
 * 本模块零依赖、零 DOM，可被 vitest 直接 import 做纯函数测试。
 */

/** 单块思考/输出正文上限：64KB（§10.4 / R12）。 */
export const MAX_THINKING_BYTES = 64 * 1024;

/** 所有事件类型（供 stream.js 注册 EventSource 监听用）。 */
export const SOLVEX_EVENT_TYPES = [
  "status", "step", "done", "info", "warn", "artifact", "complete", "error",
  "stage", "barrier", "thinking", "output", "tool", "turn", "model", "usage",
  "lifecycle", "ping",
];

/* ── 通用小工具（纯函数） ───────────────────────────────────────── */

/** 不依赖 TextEncoder 的 UTF-8 字节长度，纯函数、Node/浏览器通用。 */
export function utf8ByteLength(str) {
  let bytes = 0;
  for (const ch of String(str ?? "")) {
    const c = ch.codePointAt(0);
    if (c <= 0x7f) bytes += 1;
    else if (c <= 0x7ff) bytes += 2;
    else if (c <= 0xffff) bytes += 3;
    else bytes += 4;
  }
  return bytes;
}

/** 数字千分位（避免依赖运行时 locale）。 */
export function groupDigits(n) {
  return String(n ?? 0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** 单块正文超 64KB 时按 UTF-8 字节安全截断，并给出 truncated 标记。 */
export function truncateThinking(content, maxBytes = MAX_THINKING_BYTES) {
  const s = String(content ?? "");
  const bytes = utf8ByteLength(s);
  if (bytes <= maxBytes) return { content: s, truncated: false, bytes };
  let out = "";
  let used = 0;
  for (const ch of s) {
    const n = utf8ByteLength(ch);
    if (used + n > maxBytes) break;
    out += ch;
    used += n;
  }
  return { content: out, truncated: true, bytes, keptBytes: used };
}

function num(v) { return typeof v === "number" && Number.isFinite(v) ? v : 0; }

export function zeroUsage() {
  return { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0 };
}

function addUsage(a, b) {
  return {
    input: num(a.input) + num(b.input),
    output: num(a.output) + num(b.output),
    cacheRead: num(a.cacheRead) + num(b.cacheRead),
    cacheWrite: num(a.cacheWrite) + num(b.cacheWrite),
    totalTokens: num(a.totalTokens) + num(b.totalTokens),
    cost: num(a.cost) + num(b.cost),
  };
}

/** 单个 task 的初始数据结构。 */
export function emptyTask() {
  return {
    thinkingBlocks: {}, // key: contentIndex
    turns: [],           // turn 事件序列
    tools: {},           // key: toolCallId
    output: {},          // key: contentIndex
    lifecycle: [],       // lifecycle 事件序列
    model: null,
  };
}

/* ── createStore ────────────────────────────────────────────────── */

/**
 * 初始状态。stages/tasks/usage.byTask 均为普通对象（Map/对象语义），
 * 全部更新走不可变替换。
 */
export function createStore() {
  return {
    config: {},                  // 当前模型/thinking 等配置快照
    stages: {},                  // node.id -> StageNode
    barriers: {},                // barrier.id -> { id, state, completed, total, ts }
    tasks: {},                   // taskId -> { thinkingBlocks, turns, tools, output, lifecycle, model }
    usage: { global: zeroUsage(), byTask: {} },
    events: [],                  // 原始 SolveXEvent（已过滤 ping）
    artifacts: [],               // artifact 事件里的路径
    model: null,                 // 顶部条：{ provider, model, thinkingLevel, ts }
    status: "idle",              // idle | running | completed | failed | aborted
    summary: null,               // complete.result
    error: null,
  };
}

/* ── 子 reducer（均为纯函数，返回新对象） ────────────────────────── */

/** 不可变地更新某个 task；不存在则新建。 */
function updateTask(state, taskId, updater) {
  const id = taskId || "__unknown__";
  const tasks = { ...state.tasks };
  tasks[id] = updater(tasks[id] ? { ...tasks[id] } : emptyTask());
  return { ...state, tasks };
}

/** 按 node.id upsert / remove；node.state 是阶段状态的唯一权威来源。 */
function applyStage(state, e) {
  const node = e.node || {};
  const id = node.id;
  if (!id) return state;
  const stages = { ...state.stages };
  if (e.op === "remove") {
    delete stages[id];
  } else {
    // 增量 patch：与已有节点浅合并，整节点与部分 patch 都能正确工作。
    stages[id] = { ...(stages[id] || {}), ...node };
  }
  return { ...state, stages };
}

/** barrier 事件更新 completed / total / state。 */
function applyBarrier(state, e) {
  const id = e.id;
  if (!id) return state;
  const barriers = {
    ...state.barriers,
    [id]: {
      id,
      state: e.state || "waiting",
      completed: num(e.completed),
      total: num(e.total),
      ts: e.ts,
    },
  };
  return { ...state, barriers };
}

/**
 * 思考块 reducer（以 contentIndex 为 key）。
 * - start：新建折叠块；
 * - delta：按 contentIndex 追加（超 64KB 截断）；
 * - end：content 为权威值，【必须覆盖】 delta 拼接结果；redacted 优雅降级。
 */
export function reduceThinkingBlocks(blocks, e) {
  const key = String(e.contentIndex ?? 0);
  const prev = blocks[key] || {
    contentIndex: e.contentIndex ?? 0,
    blockId: e.blockId,
    taskId: e.taskId,
    content: "",
    state: "start",
    redacted: false,
    truncated: false,
    startedAt: null,
    endedAt: null,
    charCount: 0,
  };
  let next;
  if (e.state === "start") {
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      state: "streaming",
      redacted: !!e.redacted,
      startedAt: e.ts ?? prev.startedAt,
    };
  } else if (e.state === "delta") {
    const t = truncateThinking(prev.content + (e.delta || ""));
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      content: t.content,
      truncated: t.truncated,
      state: "streaming",
      charCount: t.content.length,
    };
  } else if (e.state === "end") {
    // 权威覆盖：thinking_end.content 优先于所有 delta 拼接结果。
    const authority = e.content != null ? e.content : prev.content;
    const t = truncateThinking(authority);
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      content: t.content,
      truncated: t.truncated,
      state: "end",
      redacted: e.redacted ?? prev.redacted,
      endedAt: e.ts ?? prev.endedAt,
      charCount: t.content.length,
    };
  } else {
    next = { ...prev };
  }
  const out = { ...blocks, [key]: next };
  return out;
}

/**
 * 输出块 reducer（以 contentIndex 为 key）。
 * - delta：追加临时文本；
 * - end：content 权威值覆盖 delta；
 * - final（message_end）：message 为权威值，覆盖整个 partial 消息。
 */
export function reduceOutputBlocks(blocks, e) {
  const key = String(e.contentIndex ?? 0);
  const prev = blocks[key] || {
    contentIndex: e.contentIndex ?? 0,
    blockId: e.blockId,
    content: "",
    message: null,
    state: "streaming",
    authoritative: false,
  };
  let next;
  if (e.state === "delta") {
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      content: prev.content + (e.delta || ""),
      state: "streaming",
    };
  } else if (e.state === "end") {
    // output 的 state:"end" 的 content 覆盖 delta。
    const authority = e.content != null ? e.content : prev.content;
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      content: authority,
      state: "end",
      authoritative: true,
    };
  } else if (e.state === "final") {
    // message_end：用权威 message 覆盖 partial；无 content 时用字符串消息兜底。
    const authority = e.content != null
      ? e.content
      : (typeof e.message === "string" ? e.message : prev.content);
    next = {
      ...prev,
      blockId: e.blockId ?? prev.blockId,
      content: authority,
      message: e.message ?? prev.message,
      state: "final",
      authoritative: true,
    };
  } else {
    next = { ...prev };
  }
  return { ...blocks, [key]: next };
}

function applyThinking(state, e) {
  return updateTask(state, e.taskId, (task) => ({
    ...task,
    thinkingBlocks: reduceThinkingBlocks(task.thinkingBlocks, e),
  }));
}

function applyOutput(state, e) {
  return updateTask(state, e.taskId, (task) => ({
    ...task,
    output: reduceOutputBlocks(task.output, e),
  }));
}

/** tool 事件按 toolCallId 归入对应 task。 */
function applyTool(state, e) {
  return updateTask(state, e.taskId, (task) => {
    const tools = { ...task.tools };
    const id = e.toolCallId || "unknown";
    const prev = tools[id] || { toolCallId: id, name: e.name, partial: "" };
    let partial = prev.partial || "";
    if (e.state === "delta" && e.partialResult != null) {
      partial += String(e.partialResult);
    }
    tools[id] = {
      ...prev,
      name: e.name ?? prev.name,
      state: e.state,
      args: e.args ?? prev.args,
      partialResult: e.partialResult ?? prev.partialResult,
      result: e.result ?? prev.result,
      isError: e.isError ?? prev.isError,
      durationMs: e.durationMs ?? prev.durationMs,
      partial,
      ts: e.ts,
    };
    return { ...task, tools };
  });
}

/** turn 事件归入对应 task。 */
function applyTurn(state, e) {
  return updateTask(state, e.taskId, (task) => ({
    ...task,
    turns: [...task.turns, { state: e.state, turn: e.turn, ts: e.ts }],
  }));
}

/**
 * usage 事件做两级汇总（按任务 + 全局）。
 * 事件字段：input/output/cacheRead/cacheWrite/totalTokens/cost —— 求和即可，
 * 事件里已无 reasoning 字段，【绝不重复累加】。
 * cumulative=true 视为该任务的累计快照（覆盖而非再加，避免重复计数）。
 * 全局值始终由 byTask 重新求和，保证两级一致。
 */
function applyUsage(state, e) {
  const byTask = { ...state.usage.byTask };
  const key = e.taskId || "__global__";
  const inc = {
    input: num(e.input),
    output: num(e.output),
    cacheRead: num(e.cacheRead),
    cacheWrite: num(e.cacheWrite),
    totalTokens: num(e.totalTokens),
    cost: num(e.cost),
  };
  byTask[key] = e.cumulative
    ? { ...zeroUsage(), ...inc }
    : addUsage(byTask[key] || zeroUsage(), inc);
  let global = zeroUsage();
  for (const k of Object.keys(byTask)) global = addUsage(global, byTask[k]);
  return { ...state, usage: { global, byTask } };
}

/** model 事件刷新顶部条，并记入对应 task。 */
function applyModel(state, e) {
  const model = {
    provider: e.provider,
    model: e.model,
    thinkingLevel: e.thinkingLevel ?? state.model?.thinkingLevel,
    ts: e.ts,
  };
  let next = { ...state, model };
  if (e.taskId) {
    next = updateTask(next, e.taskId, (task) => ({ ...task, model }));
  }
  return next;
}

/**
 * lifecycle 事件【仅记录】，绝不改动任何阶段状态、绝不把 run 标为完成。
 * agent_end / agent_settled 都只是会话细节；阶段权威状态只来自 stage 事件。
 */
function applyLifecycle(state, e) {
  return updateTask(state, e.taskId, (task) => ({
    ...task,
    lifecycle: [...task.lifecycle, { state: e.state, detail: e.detail, ts: e.ts }],
  }));
}

/** artifact 事件记录产物路径（真实文件树由 /api/artifacts 提供）。 */
function applyArtifact(state, e) {
  if (!e.path) return state;
  return { ...state, artifacts: [...state.artifacts, e.path] };
}

/* ── 主 reducer ─────────────────────────────────────────────────── */

function applyOne(state, e) {
  switch (e.type) {
    case "stage": return applyStage(state, e);
    case "barrier": return applyBarrier(state, e);
    case "thinking": return applyThinking(state, e);
    case "output": return applyOutput(state, e);
    case "tool": return applyTool(state, e);
    case "turn": return applyTurn(state, e);
    case "usage": return applyUsage(state, e);
    case "model": return applyModel(state, e);
    case "lifecycle": return applyLifecycle(state, e);
    case "artifact": return applyArtifact(state, e);
    case "complete":
      // 只有 complete 事件把 run 标为完成。
      return { ...state, status: e.result?.status ?? "completed", summary: e.result ?? null };
    case "error":
      return { ...state, status: "failed", error: e.message ?? null };
    case "status": case "step": case "done": case "info": case "warn":
      // 兼容旧版：仅进 events[]（由外层统一追加），不影响阶段/完成判定。
      return state;
    default:
      return state;
  }
}

/**
 * 纯函数：把一条 SolveXEvent 折叠进 state，返回全新对象。
 * - ping 直接忽略（不进 store、不进 events[]）；
 * - 其余事件统一追加进 events[] 供「日志」标签页回放；
 * - 首条真实事件把 idle 提升为 running。
 */
export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  if (event.type === "ping") return state; // ping 不进 store
  let next = applyOne(state, event);
  next = { ...next, events: [...next.events, { ...event }] };
  if (next.status === "idle") next = { ...next, status: "running" };
  return next;
}
