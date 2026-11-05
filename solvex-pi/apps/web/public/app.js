/* SolveX WebUI 2.0 —— 应用组装入口（原生 ESM，浏览器直接加载）。
 * 负责：单一 SessionStore 的 dispatch、标签页切换、新建会话、历史列表、
 * 中止、刷新回放、启动运行、模型配置抽屉、隐藏思考开关。
 * 所有视图渲染委托给 modules/*，渲染入口做 rAF 合并以节流高频 delta。
 */
import { createStore, reduce } from "./modules/store.js";
import { connect } from "./modules/stream.js";
import { renderModelStudio, loadModels } from "./modules/models.js";
import { renderThinking } from "./modules/thinking.js";
import { renderTimeline, renderStages } from "./modules/stages.js";
import {
  renderUsageBar, renderArtifacts, loadArtifacts, startRun,
} from "./modules/artifacts.js";

/* ── 应用状态 ───────────────────────────────────────────────────── */
let state = createStore();
let sessionId = null;
let streamHandle = null;
let pendingFiles = [];
let activeTab = "stages";
let hideThinking = false;
let artifactsPayload = null;
const collapsed = new Set();   // 思考块折叠状态，key = taskId:contentIndex
const expanded = new Set();    // 阶段节点展开状态，key = node.id
let renderQueued = false;

const $ = (id) => document.getElementById(id);

/* ── dispatch + 渲染调度 ────────────────────────────────────────── */

function dispatch(event) {
  state = reduce(state, event);
  scheduleRender();
}

function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => { renderQueued = false; renderAll(); });
}

function renderAll() {
  renderUsageBar($("topbar"), state);
  const sessionEl = $("bar-session");
  if (sessionEl) sessionEl.textContent = sessionId ? `会话 ${sessionId}` : "未开始";

  renderTimeline($("rightbar"), state, {
    expanded,
    onToggle: toggleStage,
  });

  const stagePanel = $("panel-stages");
  if (stagePanel) renderStages(stagePanel, state, { expanded, onToggle: toggleStage });

  const thinkPanel = $("panel-thinking");
  if (thinkPanel) renderThinking(thinkPanel, state, {
    hideThinking, collapsed, onToggle: toggleThinking,
  });

  renderLog($("panel-log"));

  const artPanel = $("panel-artifacts");
  if (artPanel) renderArtifacts(artPanel, artifactsPayload, sessionId);

  const abortBtn = $("btn-abort");
  if (abortBtn) abortBtn.disabled = !(sessionId && state.status === "running");
}

function renderLog(root) {
  if (!root) return;
  root.replaceChildren();
  const pre = document.createElement("pre");
  pre.className = "log-pre";
  pre.textContent = state.events.slice(-400).map((e) => JSON.stringify(e)).join("\n") || "（暂无事件）";
  root.append(pre);
}

/* ── 交互回调 ───────────────────────────────────────────────────── */

function toggleThinking(key) {
  if (collapsed.has(key)) collapsed.delete(key);
  else collapsed.add(key);
  scheduleRender();
}

function toggleStage(id) {
  if (expanded.has(id)) expanded.delete(id);
  else expanded.add(id);
  scheduleRender();
}

function setTab(tab) {
  activeTab = tab;
  document.querySelectorAll("#tabs .tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll("#panels .panel").forEach((p) =>
    p.classList.toggle("active", p.id === `panel-${tab}`));
}

/* ── 会话生命周期 ───────────────────────────────────────────────── */

function closeStream() {
  if (streamHandle) { streamHandle.close(); streamHandle = null; }
}

function openStream(id, since = 0) {
  closeStream();
  streamHandle = connect(id, {
    since,
    onEvent: dispatch,
    onStages: (nodes) => {
      for (const node of nodes) {
        dispatch({ type: "stage", op: "upsert", node, ts: Date.now() });
      }
    },
    onError: () => { /* 连接错误由 EventSource 自动重连处理 */ },
  });
}

function newSession() {
  closeStream();
  state = createStore();
  sessionId = null;
  artifactsPayload = null;
  pendingFiles = [];
  collapsed.clear();
  expanded.clear();
  if ($("input-text")) $("input-text").value = "";
  renderFileList();
  scheduleRender();
}

async function loadSession(id) {
  closeStream();
  state = createStore();
  sessionId = id;
  artifactsPayload = null;
  collapsed.clear();
  expanded.clear();
  scheduleRender();
  // 刷新回放：stream.connect 会先拉 /api/events?since + /api/stages 再接 SSE。
  openStream(id, 0);
  try { artifactsPayload = await loadArtifacts(id); } catch { artifactsPayload = null; }
  scheduleRender();
}

async function abortRun() {
  if (!sessionId) return;
  try { await fetch(`/api/abort/${encodeURIComponent(sessionId)}`, { method: "POST" }); }
  catch { /* 忽略网络错误 */ }
}

async function start() {
  const text = $("input-text")?.value?.trim() || "";
  if (!text) { alert("请输入问题文本"); return; }
  const concurrency = Number($("input-concurrency")?.value || 3);
  const strict = !!$("input-strict")?.checked;
  try {
    const id = await startRun({ text, files: pendingFiles, concurrency, strict });
    if (!id) { alert("启动失败：未返回 session_id"); return; }
    sessionId = id;
    state = createStore();
    artifactsPayload = null;
    scheduleRender();
    openStream(id, 0);
    refreshSessions();
  } catch (err) {
    alert(`启动失败：${err.message}`);
  }
}

/* ── 历史会话列表 ───────────────────────────────────────────────── */

function normalizeSessions(payload) {
  const list = Array.isArray(payload) ? payload : (payload?.sessions || []);
  return list.slice().reverse(); // 倒序（新会话在上）
}

async function refreshSessions() {
  const box = $("session-list");
  if (!box) return;
  try {
    const res = await fetch("/api/sessions");
    const list = normalizeSessions(await res.json());
    box.replaceChildren();
    for (const s of list) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.className = "session-item" + (s.id === sessionId ? " active" : "");
      btn.textContent = `${s.problem || s.id} · ${s.status || ""}`;
      btn.title = s.created_at || "";
      btn.onclick = () => loadSession(s.id);
      li.append(btn);
      box.append(li);
    }
    if (!list.length) box.append(Object.assign(document.createElement("li"), { className: "hint", textContent: "暂无历史会话" }));
  } catch { /* 忽略 */ }
}

/* ── 模型配置抽屉 ───────────────────────────────────────────────── */

async function openModels() {
  const drawer = $("model-drawer");
  if (!drawer) return;
  drawer.classList.add("open");
  try {
    const data = await loadModels();
    renderModelStudio($("model-studio"), data, {
      onClose: closeModels,
      onRefresh: openModels,
      onSaved: closeModels,
      onChange: (cfg) => { state = { ...state, config: { ...state.config, ...cfg } }; },
    });
  } catch (err) {
    const host = $("model-studio");
    if (host) host.textContent = `加载模型配置失败：${err.message}`;
  }
}

function closeModels() {
  $("model-drawer")?.classList.remove("open");
}

/* ── 文件拖拽 / 选择 ────────────────────────────────────────────── */

function addFiles(fileList) {
  for (const f of Array.from(fileList || [])) pendingFiles.push(f);
  renderFileList();
}

function renderFileList() {
  const box = $("file-list");
  if (!box) return;
  box.replaceChildren();
  pendingFiles.forEach((f, i) => {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.textContent = f.name;
    const x = document.createElement("button");
    x.className = "chip-x";
    x.textContent = "×";
    x.onclick = () => { pendingFiles.splice(i, 1); renderFileList(); };
    chip.append(x);
    box.append(chip);
  });
}

function bindDropzone() {
  const dz = $("dropzone");
  const input = $("input-files");
  if (input) input.onchange = () => addFiles(input.files);
  if (!dz) return;
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag");
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  });
}

/* ── 初始化 ─────────────────────────────────────────────────────── */

function init() {
  document.querySelectorAll("#tabs .tab").forEach((b) =>
    b.addEventListener("click", () => setTab(b.dataset.tab)));
  setTab(activeTab);

  $("btn-start")?.addEventListener("click", start);
  $("btn-new")?.addEventListener("click", newSession);
  $("btn-abort")?.addEventListener("click", abortRun);
  $("btn-models")?.addEventListener("click", openModels);
  $("drawer-close")?.addEventListener("click", closeModels);

  const hide = $("hide-thinking");
  if (hide) hide.onchange = () => { hideThinking = hide.checked; scheduleRender(); };

  const conc = $("input-concurrency");
  if (conc) conc.oninput = () => { const v = $("concurrency-val"); if (v) v.textContent = conc.value; };

  bindDropzone();
  refreshSessions();
  scheduleRender();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}
