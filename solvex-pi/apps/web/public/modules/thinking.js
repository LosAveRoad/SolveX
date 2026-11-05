/* SolveX WebUI 2.0 —— 思考过程视图。
 * 默认折叠（摘要行显示字数/耗时）、按 contentIndex 追加、redacted 优雅降级、
 * 单块 >64KB 截断标记、全局「隐藏思考」开关、并行任务按 taskId 分栏不混淆。
 * 本模块复用 store.js 的纯函数块 reducer，并补充视图层纯函数与 DOM 渲染。
 */
import {
  reduceThinkingBlocks, truncateThinking, utf8ByteLength,
  MAX_THINKING_BYTES, groupDigits,
} from "./store.js";

export {
  reduceThinkingBlocks, truncateThinking, utf8ByteLength,
  MAX_THINKING_BYTES, groupDigits,
};

/* ── 视图层纯函数 ───────────────────────────────────────────────── */

export function isRedacted(block) {
  return !!(block && block.redacted);
}

/** 折叠块默认收起。 */
export function defaultCollapsed() { return true; }
export function toggleFold(prev) { return !prev; }

/** 折叠摘要行：字数 / 耗时 / 点击展开；redacted 显示降级提示。 */
export function blockSummary(block = {}) {
  const chars = block.charCount ?? (block.content ? block.content.length : 0);
  const start = block.startedAt;
  const end = block.endedAt;
  const durationMs = (start && end && end >= start) ? (end - start) : 0;
  const durText = durationMs > 0 ? `${(durationMs / 1000).toFixed(1)}s` : "计算中";
  if (isRedacted(block)) {
    return {
      text: "该模型的思考内容不可见 · 点击展开",
      chars, durationMs, redacted: true,
    };
  }
  return {
    text: `思考 ${durText} · ${groupDigits(chars)} 字 · 点击展开`,
    chars, durationMs, redacted: false,
  };
}

/** 按 taskId 把思考块分组，保证并行任务分栏不混淆。 */
export function groupThinkingByTask(state = {}) {
  const out = {};
  const tasks = state.tasks || {};
  for (const [taskId, task] of Object.entries(tasks)) {
    const blocks = Object.values((task && task.thinkingBlocks) || {});
    if (blocks.length) out[taskId] = blocks;
  }
  return out;
}

/** 对单个块应用一条 thinking 事件（返回新块），便于视图层独立测试。 */
export function applyThinkingEvent(blocks, event) {
  return reduceThinkingBlocks(blocks || {}, event);
}

/* ── 浏览器侧（DOM 仅在函数体内使用） ───────────────────────────── */

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/** 渲染思考过程视图。opts: { hideThinking, collapsed:Set }。 */
export function renderThinking(root, state, opts = {}) {
  if (!root) return;
  root.replaceChildren();

  if (opts.hideThinking) {
    root.append(el("p", "hint", "已开启「隐藏思考」，思考内容不会显示。"));
    return;
  }

  const grouped = groupThinkingByTask(state);
  const taskIds = Object.keys(grouped);
  if (!taskIds.length) {
    root.append(el("p", "hint", "暂无思考过程。选择支持 reasoning 的模型后，思考块会流式出现在这里。"));
    return;
  }

  const columns = el("div", "thinking-columns");
  for (const taskId of taskIds) {
    const col = el("div", "thinking-col");
    col.append(el("h3", "col-title", `任务 ${taskId}`));
    const blocks = grouped[taskId].slice().sort(
      (a, b) => Number(a.contentIndex ?? 0) - Number(b.contentIndex ?? 0));
    for (const block of blocks) {
      const key = `${taskId}:${block.contentIndex}`;
      const collapsed = opts.collapsed ? opts.collapsed.has(key) : defaultCollapsed();
      const card = el("div", "thinking-block" + (collapsed ? " collapsed" : ""));
      const summary = blockSummary(block);
      const head = el("div", "thinking-summary", summary.text);
      if (block.truncated) head.append(el("span", "badge warn", "已截断 64KB"));
      if (summary.redacted) head.classList.add("redacted");
      head.onclick = () => { if (opts.onToggle) opts.onToggle(key); };
      const body = el("pre", "thinking-body");
      body.textContent = summary.redacted
        ? "该模型的思考内容不可见（redacted）。"
        : (block.content || "");
      card.append(head, body);
      col.append(card);
    }
    columns.append(col);
  }
  root.append(columns);
}
