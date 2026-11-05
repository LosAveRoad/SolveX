/* SolveX WebUI 2.0 —— 产物视图 + 顶部实时用量条 + 启动运行。
 * 真实文件树来自 GET /api/artifacts/{id}，预览 + ZIP 下载 GET /api/download/{id}。
 * 关键修复（Q-Web）：startRun() 用 FormData 提交到 POST /api/run，
 * 【不手动设置 Content-Type】，避免旧版 JSON/multipart 不一致 bug。
 */

/* ── 纯函数 ─────────────────────────────────────────────────────── */

export function groupDigits(n) {
  return String(n ?? 0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export function formatTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

export function formatCost(n) {
  return `¥${(Number(n) || 0).toFixed(2)}`;
}

/** 顶部条视图模型：模型 / thinking / token / ¥，全部来自 store 状态。 */
export function buildUsageBar(state = {}) {
  const g = state.usage?.global || {};
  const m = state.model || {};
  const cfg = state.config || {};
  return {
    status: state.status || "idle",
    model: m.model ? `${m.provider ? m.provider + "/" : ""}${m.model}` : "—",
    thinking: m.thinkingLevel || cfg.defaults?.thinkingLevel || "off",
    input: formatTokens(g.input || 0),
    output: formatTokens(g.output || 0),
    tokens: formatTokens(g.totalTokens || 0),
    cost: formatCost(g.cost || 0),
  };
}

/** 把扁平路径数组还原成文件树。 */
export function buildFileTree(paths = []) {
  const root = { name: "", path: "", type: "dir", children: [] };
  for (const p of paths || []) {
    const parts = String(p).split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1 && /\.[^./]+$/.test(part);
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          path: parts.slice(0, i + 1).join("/"),
          type: isFile ? "file" : "dir",
          children: [],
        };
        node.children.push(child);
      }
      node = child;
    });
  }
  return root;
}

/** 从 /api/artifacts 的多种响应形态中提取路径数组。 */
export function normalizeArtifacts(payload) {
  if (Array.isArray(payload)) {
    return payload.map((p) => (typeof p === "string" ? p : p?.path)).filter(Boolean);
  }
  if (Array.isArray(payload?.files)) {
    return payload.files.map((p) => (typeof p === "string" ? p : p?.path)).filter(Boolean);
  }
  if (Array.isArray(payload?.tree)) return normalizeArtifacts(payload.tree);
  if (payload && typeof payload === "object") {
    return Object.keys(payload).filter((k) => k && k !== "children");
  }
  return [];
}

/** 构造 multipart 表单的键值条目（纯函数，便于测试；不依赖 FormData）。 */
export function toFormEntries(opts = {}) {
  const entries = [["text", String(opts.text ?? "")]];
  for (const f of opts.files || []) entries.push(["files[]", f]);
  if (opts.concurrency != null) entries.push(["concurrency", String(opts.concurrency)]);
  if (opts.strict != null) entries.push(["strict", String(!!opts.strict)]);
  return entries;
}

/** 构造真正的 FormData（浏览器/Node22 内置）。 */
export function buildRunFormData(opts = {}) {
  const fd = new FormData();
  for (const [k, v] of toFormEntries(opts)) fd.append(k, v);
  return fd;
}

/**
 * fetch 选项：【绝不】带 headers / Content-Type，让浏览器自动设置 multipart boundary。
 * 这正是旧版 multipart bug 的修复点。
 */
export function buildFetchOptions(formData) {
  return { method: "POST", body: formData };
}

export function downloadUrl(sessionId) {
  return `/api/download/${encodeURIComponent(sessionId)}`;
}

/* ── 浏览器侧（DOM / fetch 仅在函数体内使用） ────────────────────── */

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/** 顶部实时用量条渲染。 */
export function renderUsageBar(bar, state) {
  if (!bar) return;
  const v = buildUsageBar(state);
  const set = (id, text) => { const n = document.getElementById(id); if (n) n.textContent = text; };
  set("bar-status", v.status === "running" ? "● 运行中" : v.status === "completed" ? "✓ 已完成" : v.status);
  set("bar-model", `模型 ${v.model}`);
  set("bar-thinking", `Thinking: ${v.thinking}`);
  set("bar-tokens", `输入 ${v.input} / 输出 ${v.output} / 合计 ${v.tokens}`);
  set("bar-cost", v.cost);
}

/** GET /api/artifacts/{id}。 */
export async function loadArtifacts(sessionId) {
  const res = await fetch(`/api/artifacts/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`加载产物失败：${res.status}`);
  return res.json();
}

/** 渲染产物标签页：真实文件树 + 预览 + ZIP 下载。 */
export function renderArtifacts(root, payload, sessionId, opts = {}) {
  if (!root) return;
  root.replaceChildren();
  const top = el("div", "artifact-toolbar");
  const dl = el("a", "btn primary", "下载 ZIP");
  if (sessionId) { dl.href = downloadUrl(sessionId); dl.setAttribute("download", ""); }
  else dl.classList.add("disabled");
  top.append(dl);
  root.append(top);

  const paths = normalizeArtifacts(payload);
  if (!paths.length) {
    root.append(el("p", "hint", "运行完成后，这里会显示真实产物文件树与预览。"));
    return;
  }
  const tree = buildFileTree(paths);
  const wrap = el("div", "artifact-split");
  const treeBox = el("div", "file-tree");
  const previewBox = el("pre", "file-preview", "点击左侧文件以预览。");
  const draw = (node, depth, container) => {
    for (const c of node.children.slice().sort((a, b) => a.name.localeCompare(b.name))) {
      const row = el("div", "tree-row" + (c.type === "dir" ? " dir" : " file"));
      row.style.paddingLeft = `${depth * 14}px`;
      row.textContent = (c.type === "dir" ? "▸ " : "· ") + c.name;
      if (c.type === "file") {
        row.onclick = async () => {
          const res = await fetch(`/api/artifacts/${encodeURIComponent(sessionId)}/${c.path}`);
          previewBox.textContent = res.ok ? await res.text() : `（无法预览 ${c.path}）`;
        };
      }
      container.append(row);
      if (c.type === "dir") draw(c, depth + 1, container);
    }
  };
  draw(tree, 0, treeBox);
  wrap.append(treeBox, previewBox);
  root.append(wrap);
}

/**
 * 启动运行：POST /api/run，multipart text + files[]（可带 concurrency / strict）。
 * 返回 { session_id }。绝不手动设置 Content-Type。
 */
export async function startRun(opts = {}) {
  const fd = buildRunFormData(opts);
  const res = await fetch("/api/run", buildFetchOptions(fd));
  if (!res.ok) throw new Error(`启动失败：${res.status}`);
  const data = await res.json().catch(() => ({}));
  return data.session_id || data.sessionId || null;
}
