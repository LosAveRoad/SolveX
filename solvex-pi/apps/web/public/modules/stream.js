/* SolveX WebUI 2.0 —— SSE 事件流封装。
 * 刷新回放顺序（§10.6）：先 GET /api/events/{id}?since=N 与 GET /api/stages/{id}，
 * 再接 GET /api/stream/{id}。ping 心跳不进 store；Last-Event-ID 用于断线续传。
 * 纯函数（parseSseEvent / applyEvent / replayEvents / buildUrls）可被 vitest 直接测试。
 */
import { reduce, createStore, SOLVEX_EVENT_TYPES } from "./store.js";

// 供上层复用，避免测试与页面各自拼装初始状态。
export { reduce, createStore };

/**
 * 解析一段 SSE 帧文本为 { id, event, data }。
 * 识别 id:/event:/data: 多行 data、忽略注释行(:)与空行；无有效 data 时返回 null。
 * id 即自增序号，是 Last-Event-ID 续传的依据。
 */
export function parseSseEvent(raw) {
  if (raw == null) return null;
  const text = String(raw);
  let id = null;
  let event = "message";
  const dataLines = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue; // 心跳注释 / 空行
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (!dataLines.length) return null;
  return { id, event, data: dataLines.join("\n") };
}

/** 把 SSE data 文本安全地解析成对象。 */
export function parseEventData(data) {
  if (data == null) return null;
  if (typeof data === "object") return data;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

export function isPingEvent(e) {
  return !!e && e.type === "ping";
}

/** 取出帧里的自增序号（用于构造回放 since 参数）。 */
export function frameId(payload) {
  const frame = typeof payload === "string" ? parseSseEvent(payload) : payload;
  const id = frame && (frame.id ?? frame.lastEventId);
  const n = Number(id);
  return Number.isFinite(n) ? n : null;
}

/**
 * 纯函数：把一条（SSE 帧字符串 或 事件对象）应用到 state，返回新 state。
 * ping / 非法数据 / 无 type 一律跳过，返回【同一个】state 引用（不进 store）。
 */
export function applyEvent(state, payload) {
  let event = payload;
  if (typeof payload === "string") {
    const frame = parseSseEvent(payload);
    if (!frame) return state;
    event = parseEventData(frame.data);
  }
  if (!event || typeof event !== "object" || typeof event.type !== "string") return state;
  if (isPingEvent(event)) return state; // ping 不进 store
  return reduce(state, event);
}

/** 纯函数：按序回放一批历史事件（自动过滤 ping）。 */
export function replayEvents(state, frames = []) {
  let next = state;
  for (const f of frames) next = applyEvent(next, f);
  return next;
}

/** 纯函数：构造回放/阶段快照/流的 URL；since 用于 Last-Event-ID 断线续传。 */
export function buildUrls(base, sessionId, since = 0) {
  const root = String(base || "").replace(/\/$/, "");
  const sid = encodeURIComponent(sessionId);
  return {
    events: `${root}/api/events/${sid}?since=${Number(since) || 0}`,
    stages: `${root}/api/stages/${sid}`,
    stream: `${root}/api/stream/${sid}`,
  };
}

/** 纯函数：按 since 过滤历史帧（续传时避免重复消费）。 */
export function framesSince(frames, since) {
  const n = Number(since) || 0;
  return frames.filter((f) => {
    const id = frameId(f);
    return id == null || id > n;
  });
}

/** 把 /api/stages 的快照（多种可能形态）规整成 StageNode[]。 */
export function normalizeStages(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.stages)) return payload.stages;
  if (Array.isArray(payload?.nodes)) return payload.nodes;
  if (payload && typeof payload === "object") {
    const maybe = payload.stages && typeof payload.stages === "object" && !Array.isArray(payload.stages)
      ? Object.values(payload.stages)
      : null;
    return maybe || Object.values(payload).filter((v) => v && typeof v === "object" && v.id);
  }
  return [];
}

/** 把 /api/events 的历史（多种可能形态）规整成事件数组。 */
export function normalizeEvents(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.events)) return payload.events;
  if (Array.isArray(payload?.history)) return payload.history;
  return [];
}

/**
 * 浏览器侧连接（DOM/fetch/EventSource 仅在此函数体内使用）。
 * opts: { base, since, onEvent(event), onState(patch), onStages(nodes), onError(err) }
 * - 先并行拉 events + stages 历史快照回放；
 * - 再打开 EventSource，按 SolveXEvent.type 注册监听；
 * - MessageEvent.lastEventId 记录为续传点，浏览器重连时自动携带 Last-Event-ID。
 * 返回 { close(), lastEventId }。
 */
export function connect(sessionId, opts = {}) {
  const base = opts.base || "";
  const since = Number(opts.since) || 0;
  const onEvent = opts.onEvent || (() => {});
  const onStages = opts.onStages || (() => {});
  const onError = opts.onError || (() => {});
  let lastEventId = since;
  let closed = false;
  let es = null;
  const urls = buildUrls(base, sessionId, since);

  function ingest(raw, ev) {
    if (closed) return;
    if (ev && ev.lastEventId != null) {
      const n = Number(ev.lastEventId);
      if (Number.isFinite(n)) lastEventId = Math.max(lastEventId, n);
    }
    const frame = typeof raw === "string" ? parseSseEvent(raw) : null;
    const parsed = typeof raw === "string"
      ? parseEventData(frame ? frame.data : raw)
      : raw;
    if (frame && frame.id != null) {
      const n = Number(frame.id);
      if (Number.isFinite(n)) lastEventId = Math.max(lastEventId, n);
    }
    // ping 心跳只作保活，不进 store、不触发渲染。
    if (parsed && parsed.type && !isPingEvent(parsed)) onEvent(parsed);
  }

  async function start() {
    // ① 先拉历史快照
    try {
      const [evRes, stRes] = await Promise.all([
        fetch(urls.events),
        fetch(urls.stages),
      ]);
      if (evRes.ok) {
        const events = normalizeEvents(await evRes.json());
        for (const e of events) ingest(e, null);
      }
      if (stRes.ok) onStages(normalizeStages(await stRes.json()));
    } catch (err) {
      onError(err);
    }
    if (closed) return;
    // ② 再接 SSE
    es = new EventSource(urls.stream);
    for (const type of SOLVEX_EVENT_TYPES) {
      es.addEventListener(type, (ev) => ingest(ev.data, ev));
    }
    es.onerror = (err) => { if (!closed) onError(err); };
  }

  start();

  return {
    close() { closed = true; if (es) es.close(); },
    get lastEventId() { return lastEventId; },
    get urls() { return urls; },
  };
}
