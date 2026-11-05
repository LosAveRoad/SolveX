/* SolveX WebUI 2.0 —— 运行阶段 DAG 时间线（右栏 + 阶段视图标签页）。
 * 并行节点独立刷新、屏障显示 completed/total（如 3/5）、失败标红、
 * 展开节点可见该任务的 turn / 工具 / 思考 / 输出。
 * 阶段权威状态只来自 stage 事件（store 已保证），本模块只负责视图编排。
 */

/* ── 纯函数 ─────────────────────────────────────────────────────── */

/** 扁平 StageNode[]（或对象）按 phase、id 排序，稳定输出。 */
export function orderStages(stages) {
  const arr = Array.isArray(stages)
    ? stages.slice()
    : Object.values(stages || {});
  return arr.slice().sort((a, b) =>
    (Number(a?.phase ?? 0) - Number(b?.phase ?? 0)) ||
    String(a?.id ?? "").localeCompare(String(b?.id ?? "")));
}

export function stageStateClass(node) {
  const map = {
    pending: "is-pending", queued: "is-queued", running: "is-running",
    done: "is-done", failed: "is-failed", aborted: "is-aborted", skipped: "is-skipped",
  };
  return map[node?.state] || "is-pending";
}

export function isFailed(node) { return node?.state === "failed"; }

/** 屏障标签：completed/total，如 3/5。 */
export function barrierLabel(barrier = {}) {
  return `${barrier.completed ?? 0}/${barrier.total ?? 0}`;
}

export function barrierStateClass(barrier = {}) {
  return barrier.state === "released" ? "is-done" : "is-waiting";
}

/** 用 parentId 还原父子层级（并行子节点挂在 P2 下）。 */
export function groupByParent(stages) {
  const arr = orderStages(stages);
  const byId = {};
  for (const n of arr) byId[n.id] = { node: n, children: [] };
  const roots = [];
  for (const n of arr) {
    const parent = n.parentId && byId[n.parentId];
    if (parent) parent.children.push(byId[n.id]);
    else roots.push(byId[n.id]);
  }
  return roots;
}

/** 展开节点时聚合该 task 的 turn / 工具 / 思考 / 输出。 */
export function taskDetail(node, tasks = {}) {
  const t = tasks[node?.taskId || node?.id] || {};
  const turns = (t.turns || []).slice();
  const tools = Object.values(t.tools || {});
  const thinkingBlocks = Object.values(t.thinkingBlocks || {});
  const outputBlocks = Object.values(t.output || {});
  return {
    turns, tools, thinkingBlocks, outputBlocks,
    counts: {
      turns: turns.length, tools: tools.length,
      thinking: thinkingBlocks.length, output: outputBlocks.length,
    },
  };
}

/** 构造右栏时间线行：阶段节点 + 屏障行，供渲染消费。 */
export function buildTimeline(stages, barriers) {
  const roots = groupByParent(stages);
  const rows = [];
  for (const r of roots) {
    rows.push({ kind: "node", node: r.node, children: r.children.map((c) => c.node) });
  }
  for (const b of Object.values(barriers || {})) {
    rows.push({ kind: "barrier", barrier: b });
  }
  return rows;
}

/* ── 浏览器侧（DOM 仅在函数体内使用） ───────────────────────────── */

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function nodeCard(node, detail) {
  const card = el("div", `stage-card ${stageStateClass(node)}` + (isFailed(node) ? " failed" : ""));
  const head = el("div", "stage-head");
  head.append(el("span", "stage-label", node.label || node.id));
  head.append(el("span", "stage-state", node.state));
  if (node.model) head.append(el("code", "stage-model", node.model));
  card.append(head);

  if (detail) {
    const d = el("div", "stage-detail");
    d.append(el("div", "detail-counts",
      `turn ${detail.counts.turns} · 工具 ${detail.counts.tools} · 思考 ${detail.counts.thinking} · 输出 ${detail.counts.output}`));
    for (const t of detail.tools) {
      d.append(el("div", "tool-line", `⚙ ${t.name || t.toolCallId} [${t.state}]${t.isError ? " ✗" : ""}`));
    }
    for (const b of detail.thinkingBlocks) {
      d.append(el("div", "think-line", `💭 ${b.redacted ? "内容不可见" : (b.content || "").slice(0, 120)}`));
    }
    for (const o of detail.outputBlocks) {
      d.append(el("div", "out-line", `▸ ${String(o.content || "").slice(0, 160)}`));
    }
    card.append(d);
  }
  return card;
}

/** 渲染右栏时间线（compact=true 时只画紧凑节点，不展开明细）。 */
export function renderTimeline(root, state, opts = {}) {
  if (!root) return;
  root.replaceChildren();
  const rows = buildTimeline(state.stages || {}, state.barriers || {});
  if (!rows.length) {
    root.append(el("p", "hint", "运行开始后，这里会显示 P1 → P2(并行) → P3 → P4 的阶段时间线。"));
    return;
  }
  for (const row of rows) {
    if (row.kind === "barrier") {
      const b = el("div", `barrier ${barrierStateClass(row.barrier)}`);
      b.append(el("span", "", `屏障 ${row.barrier.id}`));
      b.append(el("strong", "barrier-count", barrierLabel(row.barrier)));
      root.append(b);
      continue;
    }
    const wrap = el("div", "stage-group");
    wrap.append(nodeCard(row.node, null));
    for (const child of row.children) {
      const detail = opts.expanded && opts.expanded.has(child.id)
        ? taskDetail(child, state.tasks || {}) : null;
      const c = nodeCard(child, detail);
      c.classList.add("child");
      c.onclick = () => opts.onToggle && opts.onToggle(child.id);
      wrap.append(c);
    }
    root.append(wrap);
  }
}

/** 渲染中栏「阶段视图」标签页：DAG 卡片 + 展开明细。 */
export function renderStages(root, state, opts = {}) {
  if (!root) return;
  root.replaceChildren();
  const rows = buildTimeline(state.stages || {}, state.barriers || {});
  for (const row of rows) {
    if (row.kind === "barrier") {
      const b = el("div", `barrier ${barrierStateClass(row.barrier)}`);
      b.append(el("span", "", `屏障 ${row.barrier.id}`));
      b.append(el("strong", "barrier-count", barrierLabel(row.barrier)));
      root.append(b);
      continue;
    }
    const detail = opts.expanded && opts.expanded.has(row.node.id)
      ? taskDetail(row.node, state.tasks || {}) : null;
    const card = nodeCard(row.node, detail);
    card.onclick = () => opts.onToggle && opts.onToggle(row.node.id);
    root.append(card);
    for (const child of row.children) {
      const cd = opts.expanded && opts.expanded.has(child.id)
        ? taskDetail(child, state.tasks || {}) : null;
      const c = nodeCard(child, cd);
      c.classList.add("child");
      c.onclick = () => opts.onToggle && opts.onToggle(child.id);
      root.append(c);
    }
  }
}
