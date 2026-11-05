/* SolveX WebUI 2.0 —— 模型配置中心（Model Studio）抽屉。
 * 数据来自 GET /api/models，保存走 PUT /api/models/config。
 * 安全（§10.9 / R13）：凭据只展示 masked，任何 apiKey 明文都不落到 DOM / 不回传前端。
 * 纯函数（分组 / 搜索 / 脱敏 / thinking 档位过滤 / 配置编辑）可被 vitest 直接测试。
 */

export const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];
export const PHASES = ["P1", "P2_IMPL", "P2_REVIEW", "P3", "P4"];

/* ── 纯函数 ─────────────────────────────────────────────────────── */

/** 按 provider 分组。返回 { provider: ModelDescriptor[] }。 */
export function groupByProvider(models = []) {
  const out = {};
  for (const m of models || []) {
    const p = m?.provider || "unknown";
    (out[p] ||= []).push(m);
  }
  return out;
}

/** 搜索：id / name / provider 大小写不敏感；空查询返回全部。 */
export function searchModels(models = [], query = "") {
  const q = String(query || "").trim().toLowerCase();
  const list = models || [];
  if (!q) return list.slice();
  return list.filter((m) =>
    [m?.id, m?.name, m?.provider].some((v) => String(v || "").toLowerCase().includes(q)));
}

/** API Key 脱敏：保留前 3 与后 4，中间打码；已是 masked 的原样返回。 */
export function maskApiKey(value) {
  if (!value) return "";
  const s = String(value);
  if (s.includes("••••") || s.includes("***")) return s; // 已脱敏
  if (s.length <= 8) return "••••";
  return `${s.slice(0, 3)}••••${s.slice(-4)}`;
}

/** 单条凭据投影：只暴露 provider/source/status/masked，【绝不】返回明文 apiKey。 */
export function safeCredential(cred = {}) {
  return {
    provider: cred.provider || "unknown",
    source: cred.source || "env",
    status: cred.status || "missing",
    masked: cred.masked || maskApiKey(cred.apiKey || ""),
  };
}

/** 递归剔除任何可能的明文密钥字段，用于「进 DOM 前」与「保存前」净化。 */
export function sanitizeConfig(config = {}) {
  let clone;
  try {
    clone = JSON.parse(JSON.stringify(config || {}));
  } catch {
    clone = {};
  }
  const secretKey = /^(apiKey|api_key|apikey|token|secret|password|authorization)$/i;
  const strip = (o) => {
    if (!o || typeof o !== "object") return;
    for (const k of Object.keys(o)) {
      if (secretKey.test(k)) delete o[k];
      else if (typeof o[k] === "object") strip(o[k]);
    }
  };
  strip(clone);
  return clone;
}

/** thinking 档位按模型能力裁剪：不支持 reasoning → 仅 ["off"]。 */
export function filterThinkingLevels(model, allLevels = THINKING_LEVELS) {
  if (!model || !model.reasoning) return ["off"];
  if (Array.isArray(model.thinkingLevels) && model.thinkingLevels.length) {
    return model.thinkingLevels.slice();
  }
  return allLevels.slice();
}

/** 能力标签（reasoning / vision / 上下文 / 单价）。 */
export function capabilityTags(model = {}) {
  const tags = [];
  if (model.reasoning) tags.push("reasoning");
  if ((model.input || []).includes("image")) tags.push("vision");
  if (model.contextLimit) tags.push(`${Math.round(model.contextLimit / 1000)}K 上下文`);
  if (model.price) tags.push(`¥${model.price.input}/${model.price.output} 每百万`);
  return tags;
}

/** 纯函数：设为默认。 */
export function setDefault(config = {}, provider, modelId) {
  return { ...config, defaults: { ...(config.defaults || {}), provider, model: modelId } };
}

/** 纯函数：分配到阶段。 */
export function assignToPhase(config = {}, phase, provider, modelId) {
  return {
    ...config,
    byPhase: { ...(config.byPhase || {}), [phase]: { provider, model: modelId } },
  };
}

/** 纯函数：加入循环集（去重）。 */
export function addScoped(config = {}, ref) {
  const set = new Set(config.scopedModels || []);
  if (ref) set.add(ref);
  return { ...config, scopedModels: [...set] };
}

/** 纯函数：构造 PUT /api/models/config 的载荷（已净化，无明文密钥）。 */
export function buildSavePayload(config = {}) {
  return sanitizeConfig({
    defaults: config.defaults || {},
    byPhase: config.byPhase || {},
    scopedModels: config.scopedModels || [],
    thinkingLevel: config.defaults?.thinkingLevel || "medium",
  });
}

/** 把 GET /api/models 的响应规整成 { models, config, credentials, endpoints }。 */
export function normalizeModelResponse(payload = {}) {
  const models = Array.isArray(payload.models) ? payload.models
    : Array.isArray(payload.available) ? payload.available
      : Array.isArray(payload) ? payload : [];
  const config = payload.config || payload;
  return {
    models,
    config: sanitizeConfig(config),
    credentials: (payload.credentials || config.credentials || []).map(safeCredential),
    endpoints: sanitizeConfig(payload.endpoints || config.endpoints || []),
  };
}

/* ── 浏览器侧（DOM / fetch 仅在函数体内使用） ────────────────────── */

let studioConfig = {};
let studioModels = [];

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/** GET /api/models。 */
export async function loadModels() {
  const res = await fetch("/api/models");
  if (!res.ok) throw new Error(`加载模型失败：${res.status}`);
  return normalizeModelResponse(await res.json());
}

/** PUT /api/models/config。 */
export async function saveConfig(config) {
  const res = await fetch("/api/models/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildSavePayload(config)),
  });
  if (!res.ok) throw new Error(`保存配置失败：${res.status}`);
  return res.json().catch(() => ({}));
}

/** GET /api/models/thinking-levels?model=。 */
export async function loadThinkingLevels(modelRef) {
  const res = await fetch(`/api/models/thinking-levels?model=${encodeURIComponent(modelRef)}`);
  if (!res.ok) return THINKING_LEVELS;
  const data = await res.json().catch(() => ({}));
  return Array.isArray(data.levels) ? data.levels : (Array.isArray(data) ? data : THINKING_LEVELS);
}

/**
 * 渲染模型配置中心抽屉。config 先经 sanitizeConfig 净化，
 * 明文 apiKey 字段一律不会写入 DOM；凭据只显示 credential.masked。
 */
export function renderModelStudio(root, data, handlers = {}) {
  if (!root) return;
  const norm = normalizeModelResponse(data);
  studioModels = norm.models;
  studioConfig = norm.config;

  root.replaceChildren();
  const head = el("div", "drawer-head");
  head.append(el("h2", "", "模型配置中心"));
  const closeBtn = el("button", "btn ghost", "关闭");
  closeBtn.onclick = () => handlers.onClose && handlers.onClose();
  head.append(closeBtn);
  root.append(head);

  // 搜索框
  const searchWrap = el("div", "field");
  const search = el("input", "input");
  search.placeholder = "搜索模型 / provider …";
  searchWrap.append(el("label", "", "搜索"), search);
  root.append(searchWrap);

  const listBox = el("div", "model-list");
  root.append(listBox);

  function drawList() {
    listBox.replaceChildren();
    const groups = groupByProvider(searchModels(studioModels, search.value));
    for (const [provider, models] of Object.entries(groups)) {
      listBox.append(el("h3", "provider-title", provider));
      for (const m of models) {
        const row = el("div", "model-row" + (m.available === false ? " unavailable" : ""));
        const info = el("div", "model-info");
        info.append(el("strong", "", m.name || m.id));
        info.append(el("code", "model-id", `${provider}/${m.id}`));
        const tags = el("div", "tags");
        for (const t of capabilityTags(m)) tags.append(el("span", "tag", t));
        info.append(tags);
        // thinking 档位按模型能力过滤
        const levels = filterThinkingLevels(m);
        const sel = el("select", "select");
        for (const lv of levels) {
          const o = el("option", "", lv);
          o.value = lv;
          sel.append(o);
        }
        if (levels[0] === "off" && levels.length === 1) {
          info.append(el("span", "hint", "该模型不支持 reasoning，已降为 off"));
        }
        const actions = el("div", "model-actions");
        const b1 = el("button", "btn", "设为默认");
        b1.onclick = () => { studioConfig = setDefault(studioConfig, provider, m.id); handlers.onChange && handlers.onChange(studioConfig); };
        const b2 = el("button", "btn", "加入循环集");
        b2.onclick = () => { studioConfig = addScoped(studioConfig, `${provider}/${m.id}`); handlers.onChange && handlers.onChange(studioConfig); };
        const phaseSel = el("select", "select");
        const empty = el("option", "", "分配到阶段…");
        empty.value = "";
        phaseSel.append(empty);
        for (const p of PHASES) { const o = el("option", "", p); o.value = p; phaseSel.append(o); }
        phaseSel.onchange = () => {
          if (!phaseSel.value) return;
          studioConfig = assignToPhase(studioConfig, phaseSel.value, provider, m.id);
          studioConfig.defaults = { ...(studioConfig.defaults || {}), thinkingLevel: sel.value };
          handlers.onChange && handlers.onChange(studioConfig);
        };
        actions.append(b1, b2, phaseSel, sel);
        row.append(info, actions);
        listBox.append(row);
      }
    }
  }
  search.oninput = drawList;
  drawList();

  // 凭据面板（只显示 masked，绝不写明文）
  const credBox = el("div", "cred-panel");
  credBox.append(el("h3", "provider-title", "凭据状态（仅遮蔽展示）"));
  for (const c of norm.credentials) {
    const line = el("div", "cred-line");
    line.append(el("span", "", `${c.provider} · ${c.source} · ${c.status}`));
    line.append(el("code", "masked", c.masked || "—"));
    credBox.append(line);
  }
  credBox.append(el("p", "hint", "优先级：运行时注入 > auth.json > models.json.apiKey > 环境变量。API Key 不回传前端。"));
  root.append(credBox);

  // 运行时注入 Key（用户输入通过 fetch body 提交，不落 DOM 明文、不回显）
  const keyWrap = el("div", "field");
  const keyInput = el("input", "input");
  keyInput.type = "password";
  keyInput.placeholder = "临时 API Key（仅内存，不落盘）";
  const keyBtn = el("button", "btn", "注入");
  keyBtn.onclick = async () => {
    const val = keyInput.value;
    keyInput.value = ""; // 立即清空，避免停留在 DOM
    if (!val) return;
    await fetch("/api/models/api-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: keyInput.dataset.provider || "", apiKey: val }),
    });
    handlers.onRefresh && handlers.onRefresh();
  };
  keyWrap.append(el("label", "", "运行时凭据"), keyInput, keyBtn);
  root.append(keyWrap);

  // 自定义端点表单（apiKey 支持 $ENV 插值；初始为空，绝不预填服务端明文）
  const ep = el("div", "endpoint-form");
  ep.append(el("h3", "provider-title", "自定义兼容端点"));
  const mk = (label, ph) => {
    const w = el("div", "field");
    const i = el("input", "input");
    i.placeholder = ph;
    w.append(el("label", "", label), i);
    return { w, i };
  };
  const fBase = mk("baseUrl", "https://api.example.com/v1");
  const fApi = mk("api", "openai-completions");
  const fKey = mk("apiKey", "$ENV:MY_KEY");
  const fModels = mk("models[]", "model-a, model-b");
  const epBtn = el("button", "btn", "保存并刷新");
  epBtn.onclick = async () => {
    const body = {
      baseUrl: fBase.i.value,
      api: fApi.i.value,
      apiKey: fKey.i.value, // 用户新输入，可含 $ENV；提交后立即清空
      models: fModels.i.value.split(",").map((s) => s.trim()).filter(Boolean),
    };
    fKey.i.value = "";
    await fetch("/api/models/endpoints", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await fetch("/api/models/refresh", { method: "POST" });
    handlers.onRefresh && handlers.onRefresh();
  };
  ep.append(fBase.w, fApi.w, fKey.w, fModels.w, epBtn);
  root.append(ep);

  const footer = el("div", "drawer-foot");
  const saveBtn = el("button", "btn primary", "保存配置");
  saveBtn.onclick = async () => { await saveConfig(studioConfig); handlers.onSaved && handlers.onSaved(); };
  footer.append(saveBtn);
  root.append(footer);
}
