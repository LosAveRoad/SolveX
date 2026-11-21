import { LitElement, html, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
// These imports register the actual upstream Pi components and tool renderers.
import { MessageList, loadAttachment } from '@earendil-works/pi-web-ui';
import '@earendil-works/pi-web-ui/app.css';
import { GlobalWorkerOptions } from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import type { SolveXEvent, StageNode } from '@solvex/core';
import { TranscriptAdapter } from './transcript.js';
import { runtimeLabel, canStartNewRun, hasActiveRuns, mergeRuns, findRun, isNearBottom,
  type RunView, type WorkspaceView } from './runs.js';
import './style.css';

// Keep Pi's PDF extraction entirely local, including its worker.
GlobalWorkerOptions.workerSrc = pdfWorker;
void MessageList;
type Run = RunView;
type Workspace = WorkspaceView;
type Artifact = { path: string; size: number; isDir: boolean };
const eventTypes = ['status','step','done','info','warn','artifact','complete','error','stage','barrier','thinking','output','tool','turn','model','usage','lifecycle'];
const labels: Record<string,string> = { running: '运行中', completed: '已完成', failed: '失败', aborted: '已停止', idle: '待开始', pending: '待运行', queued: '排队中', done: '已完成', skipped: '已跳过' };
const bytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(1)} MB`;
async function api<T = any>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, { ...init, headers: init.body instanceof FormData ? init.headers : { 'Content-Type':'application/json', ...init.headers } });
  const data = await res.json(); if (!res.ok) throw new Error(data.message || data.error || `请求失败 (${res.status})`); return data;
}
const post = (body: unknown = {}) => ({ method: 'POST', body: JSON.stringify(body) });

class SolveXApp extends LitElement {
  private workspaces: Workspace[] = [];
  private workspace?: Workspace;
  private sessionId?: string;
  private transcript = new TranscriptAdapter();
  private stages = new Map<string, StageNode>();
  private taskId = 'P1';
  private status = 'idle';
  private activity = '等待上传题目';
  private artifacts: Artifact[] = [];
  private preview?: { path: string; text?: string; kind?: 'image' | 'pdf' };
  private source?: EventSource;
  private lastSeq = 0;
  private usage = { tokens: 0, cost: 0 };
  private busy = false;
  private autoScroll = true;
  private error = '';
  private keyNotice = '';
  private endpointNotice = '';
  private settings = false;
  private models: any;
  private config: any;
  private mcp: any;
  private mcpPresets: any[] = [];
  private theme = localStorage.getItem('solvex-theme') || 'light';
  private refreshTimer?: ReturnType<typeof setInterval>;
  private runsTimer?: ReturnType<typeof setInterval>;
  private loadVersion = 0;
  protected createRenderRoot() { return this; }
  /** 用户手动上滚时暂停自动跟随，滚回底部后自动恢复。 */
  protected firstUpdated() {
    const el = this.querySelector('.sx-main');
    el?.addEventListener('scroll', (e) => {
      const t = e.currentTarget as HTMLElement;
      this.autoScroll = isNearBottom(t.scrollTop, t.clientHeight, t.scrollHeight);
    }, { passive: true });
  }
  /** AI 生成过程中每次渲染后把主视图滚到底部。 */
  protected updated() {
    if (this.status !== 'running' || !this.autoScroll) return;
    const el = this.querySelector('.sx-main') as HTMLElement | null;
    if (el) el.scrollTop = el.scrollHeight;
  }
  async connectedCallback() {
    super.connectedCallback(); document.documentElement.classList.toggle('dark', this.theme === 'dark');
    await this.perform(async () => {
      this.workspaces = await api('/api/workspaces');
      const saved = localStorage.getItem('solvex-workspace');
      const selected = this.workspaces.find(w => w.id === saved) ?? this.workspaces[0];
      if (selected) await this.selectWorkspace(selected.id);
    });
    this.refreshTimer = setInterval(() => { if (this.status === 'running') void this.refreshArtifacts(); }, 2500);
    // 并行运行：其他 run 没有 SSE 订阅，靠列表轮询同步状态与 runtime 摘要。
    this.runsTimer = setInterval(() => { if (this.workspace) void this.refreshRuns(); }, 4000);
  }
  disconnectedCallback() { super.disconnectedCallback(); this.source?.close(); clearInterval(this.refreshTimer); clearInterval(this.runsTimer); }
  private async refreshRuns() {
    const id = this.workspace?.id; if (!id) return;
    try {
      const fresh = await api<Run[]>(`/api/workspaces/${id}/runs`);
      if (this.workspace?.id !== id) return;
      const runs = mergeRuns(this.workspace.runs, fresh);
      this.workspace = { ...this.workspace, runs };
      this.workspaces = this.workspaces.map(w => w.id === id ? { ...w, runs } : w);
      this.requestUpdate();
    } catch { /* 列表轮询失败不打断当前 run 的 SSE */ }
  }
  private async perform(action: () => Promise<void>) {
    this.error = ''; this.busy = true; this.requestUpdate();
    try { await action(); } catch(e) { this.error = e instanceof Error ? e.message : String(e); }
    finally { this.busy = false; this.requestUpdate(); }
  }
  private async selectWorkspace(id: string) {
    this.source?.close(); const version = ++this.loadVersion;
    const workspace = await api<Workspace>(`/api/workspaces/${id}`);
    if (version !== this.loadVersion) return;
    this.workspace = workspace; localStorage.setItem('solvex-workspace', id);
    this.resetRun();
    if (this.workspace.runs[0]) await this.selectRun(this.workspace.runs[0]);
    this.requestUpdate();
  }
  private resetRun() {
    this.sessionId = undefined; this.transcript = new TranscriptAdapter(); this.stages.clear();
    this.taskId = 'P1'; this.status = 'idle'; this.artifacts = []; this.preview = undefined;
    this.lastSeq = 0; this.usage = { tokens: 0, cost: 0 }; this.activity = '等待开始建模';
    this.autoScroll = true;
  }
  private async createWorkspace(e: SubmitEvent) {
    e.preventDefault(); const form = e.currentTarget as HTMLFormElement;
    const name = String(new FormData(form).get('name') ?? '');
    await this.perform(async () => {
      const w = await api<Workspace>('/api/workspaces', post({ name }));
      this.workspaces = [w, ...this.workspaces]; form.reset(); await this.selectWorkspace(w.id);
    });
  }
  private async deleteWorkspace(id: string, name: string) {
    if (!window.confirm(`确定删除工作区「${name}」？题目、附件和全部运行记录都会永久删除，无法恢复。`)) return;
    await this.perform(async () => {
      await api(`/api/workspaces/${id}`, { method: 'DELETE' });
      if (this.workspace?.id === id) {
        this.source?.close(); this.source = undefined;
        this.workspace = undefined; localStorage.removeItem('solvex-workspace');
        this.resetRun();
      }
      this.workspaces = await api<Workspace[]>('/api/workspaces');
      if (!this.workspace && this.workspaces[0]) await this.selectWorkspace(this.workspaces[0].id);
    });
  }
  private async deleteRun(run: Run) {
    if (!window.confirm('确定删除这条运行记录？其产物与事件流会永久删除，无法恢复。')) return;
    const id = this.workspace?.id; if (!id) return;
    await this.perform(async () => {
      await api(`/api/workspaces/${id}/runs/${run.id}`, { method: 'DELETE' });
      const fresh = await api<Workspace>(`/api/workspaces/${id}`);
      this.workspace = fresh;
      this.workspaces = this.workspaces.map((w) => w.id === id ? { ...w, runs: fresh.runs } : w);
      if (this.sessionId === run.id) {
        this.source?.close(); this.source = undefined;
        this.resetRun();
        if (fresh.runs[0]) await this.selectRun(fresh.runs[0]);
      }
    });
  }
  private async upload(files: File[]) {
    const id = this.workspace?.id; if (!id || !files.length) return;
    await this.perform(async () => {
      if (files.length > 30) throw new Error('每次最多上传 30 个文件');
      const extractedTexts: Record<string,string> = {};
      for (const file of files) {
        if (file.size > 50*1024*1024) throw new Error(`${file.name} 超过 50 MB`);
        if (/\.(pdf|docx|md|txt)$/i.test(file.name)) {
          this.activity = `正在解析 ${file.name}`; this.requestUpdate();
          const attachment = await loadAttachment(file);
          const text = attachment.extractedText ?? '';
          // Pi wraps PDF/DOCX extraction with page tags; markup alone is not a problem.
          if (!text.replace(/<[^>]*>/g, '').trim()) throw new Error(`${file.name} 没有可读取的正文；扫描件请先进行 OCR`);
          extractedTexts[file.name] = text;
        }
      }
      const data = new FormData(); data.append('extractedTexts', JSON.stringify(extractedTexts));
      for (const file of files) data.append('files[]', file);
      const updated = await api<Workspace>(`/api/workspaces/${id}/files`, { method:'POST', body:data });
      if (this.workspace?.id === id) this.workspace = updated;
      this.workspaces = this.workspaces.map(w => w.id === id ? updated : w);
      this.activity = '题目文件已就绪';
    });
  }
  private async chooseProblem(filename: string) {
    await this.perform(async () => {
      this.workspace = await api(`/api/workspaces/${this.workspace!.id}/problem`, { method:'PUT', body:JSON.stringify({filename}) });
    });
  }
  /** 每次点击都是一次新运行；已有 run 在跑也不阻塞，产物/事件/配置各自独立。 */
  private async start() {
    await this.perform(async () => {
      const w = this.workspace!;
      const { session_id } = await api(`/api/workspaces/${w.id}/runs`, post());
      await this.selectRun({id:session_id, status:'running', created_at:new Date().toISOString()});
      const updated = await api<Workspace>(`/api/workspaces/${w.id}`);
      if (this.workspace?.id !== w.id) return;
      this.workspace = updated;
      this.workspaces = this.workspaces.map(x => x.id === w.id ? updated : x);
    });
  }
  private async stopRun() {
    const id = this.sessionId; if (!id) return;
    await this.perform(async () => {
      await api(`/api/abort/${id}`, post());
      if (this.sessionId !== id) return;
      this.status = 'aborted'; this.source?.close();
      await this.refreshArtifacts(); await this.refreshRuns();
    });
  }
  /** 断点续跑：同一个 run 目录重新执行，已完成的 Agent 调用从会话日志回放。 */
  private async resumeRun() {
    const id = this.sessionId; if (!id) return;
    await this.perform(async () => {
      await api(`/api/resume/${id}`, post());
      await this.selectRun({ id, status: 'running', created_at: new Date().toISOString() });
      await this.refreshRuns();
    });
  }
  private async selectRun(run: Run) {
    this.source?.close(); this.resetRun(); this.sessionId = run.id; this.status = run.status;
    const version = ++this.loadVersion;
    const replay = await api(`/api/events/${run.id}`);
    if (version !== this.loadVersion) return;
    for (const e of replay.events) this.accept(e);
    this.lastSeq = replay.lastSeq;
    await this.refreshArtifacts();
    if (version !== this.loadVersion) return;
    if (this.status === 'running') {
      this.source = new EventSource(`/api/stream/${run.id}`);
      for (const type of eventTypes) this.source.addEventListener(type, (raw) => {
        const event = raw as MessageEvent; const seq = Number(event.lastEventId);
        if (seq <= this.lastSeq || this.sessionId !== run.id) return;
        this.lastSeq = seq;
        this.accept(JSON.parse(event.data)); this.requestUpdate();
      });
      this.source.onerror = () => { if (this.status === 'running') { this.activity = '连接中断，正在自动重连…'; this.requestUpdate(); } };
    }
    this.requestUpdate();
  }
  private accept(e: SolveXEvent) {
    this.transcript.apply(e);
    if (e.type === 'stage') {
      if (e.op === 'remove') this.stages.delete(e.node.id);
      else this.stages.set(e.node.id, { ...this.stages.get(e.node.id), ...e.node });
    }
    if (e.type === 'status' || e.type === 'step') this.activity = e.message;
    if (e.type === 'usage') { this.usage.tokens += e.totalTokens; this.usage.cost += e.cost; }
    if (e.type === 'complete') { this.status = e.result.status; this.source?.close(); void this.refreshArtifacts(); }
    if (e.type === 'error') { this.error = e.message; this.status = 'failed'; this.source?.close(); }
    if (e.type === 'lifecycle' && e.state === 'aborted') { this.status = 'aborted'; this.source?.close(); }
  }
  private async refreshArtifacts() {
    const id = this.sessionId; if (!id) return;
    try {
      const files = await api<Artifact[]>(`/api/artifacts/${id}`);
      if (id === this.sessionId) { this.artifacts = files.filter(f => !f.isDir); this.requestUpdate(); }
    } catch { /* A reconnect will retry; do not replace the current transcript. */ }
  }
  private artifactUrl(path: string) { return `/api/artifacts/${this.sessionId}/${path.split('/').map(encodeURIComponent).join('/')}`; }
  private async openArtifact(file: Artifact) {
    await this.perform(async () => {
      if (/\.(png|jpe?g|webp|gif|svg|pdf)$/i.test(file.path)) { this.preview = {path:file.path,kind:/\.pdf$/i.test(file.path)?'pdf':'image'}; return; }
      if (file.size > 2*1024*1024) throw new Error('此文件较大，请下载工作区后查看');
      const res = await fetch(this.artifactUrl(file.path)); if (!res.ok) throw new Error('无法读取文件');
      this.preview = { path:file.path, text:await res.text() };
    });
  }
  private async openSettings() {
    await this.perform(async () => {
      const models = await api('/api/models');
      this.models = models; this.config = structuredClone(models.config);
      this.settings = true; // 先打开面板，避免 MCP 连接慢时点了设置像没反应
      // MCP 状态异步补充即可，模板里已有 mcp? / mcpPresets 的兜底。
      void Promise.all([api('/api/mcp'), api('/api/mcp/presets')])
        .then(([mcp, presets]) => {
          this.mcp = mcp; this.mcpPresets = presets.presets ?? []; this.requestUpdate();
        }).catch(() => { /* MCP 状态不影响凭据设置 */ });
    });
  }
  private async saveMcp(e: SubmitEvent) {
    e.preventDefault(); const data = new FormData(e.currentTarget as HTMLFormElement);
    await this.perform(async () => {
      let parsed: unknown;
      try { parsed = JSON.parse(String(data.get('config') ?? '')); }
      catch { throw new Error('mcp.json 不是合法 JSON'); }
      this.mcp = await api('/api/mcp', { method: 'PUT', body: JSON.stringify(parsed) });
    });
  }
  private async refreshMcp() {
    await this.perform(async () => {
      const [mcp, presets] = await Promise.all([api('/api/mcp/refresh', post()), api('/api/mcp/presets')]);
      this.mcp = mcp; this.mcpPresets = presets.presets ?? [];
    });
  }
  private async enableMcpPreset(id: string) {
    await this.perform(async () => {
      const [mcp, presets] = await Promise.all([
        api(`/api/mcp/presets/${encodeURIComponent(id)}`, post()), api('/api/mcp/presets')]);
      this.mcp = mcp; this.mcpPresets = presets.presets ?? [];
    });
  }
  private async saveConfig(e: SubmitEvent) {
    e.preventDefault(); const data = new FormData(e.currentTarget as HTMLFormElement);
    await this.perform(async () => {
      // 模型 ID 由用户直接填写，不再从内置 catalog 里选择。
      const [provider, ...modelParts] = String(data.get('model') ?? '').split('/');
      const thinkingLevel = String(data.get('thinking') ?? 'off');
      const defaults = { provider: provider || '', model: modelParts.join('/') || '', thinkingLevel };
      // 取消按阶段模型选择：所有阶段统一用用户填写的模型，避免配置里残留旧模型名。
      const byPhase = Object.fromEntries(['P1','P2_IMPL','P2_REVIEW','P3','P4']
        .map((phase) => [phase, { provider: defaults.provider, model: defaults.model, thinkingLevel }]));
      await api('/api/models/config', { method:'PUT', body:JSON.stringify({ defaults, byPhase,
        concurrency:Number(data.get('concurrency')), strict:data.get('strict') === 'on' }) });
      this.settings = false;
    });
  }
  private async saveEndpoint(e: SubmitEvent) {
    e.preventDefault(); const d = new FormData(e.currentTarget as HTMLFormElement);
    const num = (k: string) => Number(d.get(k)) || 0;
    await this.perform(async () => {
      const payload = {
        id: String(d.get('id') ?? ''), baseUrl: String(d.get('baseUrl') ?? ''),
        api: String(d.get('api') ?? 'openai-completions'), apiKey: String(d.get('keyEnvVar') ?? ''),
        models: String(d.get('models') ?? '').split(',').map((x) => x.trim()).filter(Boolean),
        contextWindow: num('contextWindow'), maxTokens: num('maxTokens'),
        reasoning: d.get('reasoning') === 'on', vision: d.get('vision') === 'on',
        cost: { input: num('costInput'), output: num('costOutput'), cacheRead: 0, cacheWrite: 0 },
      };
      await api('/api/models/endpoints', { method:'PUT', body:JSON.stringify(payload) });
      this.models = await api('/api/models');
      this.endpointNotice = '已保存模型端点与参数，运行时已刷新。';
    });
  }
  private async setKey(e: SubmitEvent) {
    e.preventDefault(); const form = e.currentTarget as HTMLFormElement; const data = new FormData(form);
    const persist = data.get('persist') === 'on';
    await this.perform(async () => {
      const res = await api('/api/models/api-key', post({ provider:data.get('provider'), apiKey:data.get('key'), persist }));
      form.reset(); this.models = await api('/api/models');
      this.keyNotice = !res.persisted
        ? '已设置，仅对当前服务进程生效；重启后需要重新填写。'
        : res.runtimeInjected === false
          ? '已保存到项目根 .env，但本次运行时注入失败，重启服务后即可生效。'
          : '已保存到项目根 .env，重启服务后自动生效（该文件不进版本库）。';
    });
  }
  private settingsView() {
    if (!this.settings || !this.models) return nothing;
    const ep = this.models.endpoints?.[0] ?? {};
    return html`<div class="sx-overlay" @click=${(e:Event) => { if(e.target===e.currentTarget) {this.settings=false;this.requestUpdate();} }}><section class="sx-dialog" role="dialog" aria-modal="true" aria-label="模型设置">
      <header><h2>模型与运行设置</h2><button aria-label="关闭设置" @click=${()=>{this.settings=false;this.requestUpdate();}}>×</button></header>
      <details open><summary>模型凭据 / API Key</summary><p class="sx-muted">可直接填写 API Key。勾选「保存到 .env」会写入项目根 .env（权限 600、不进版本库），重启后自动生效；不勾选则仅对当前服务进程生效。</p><form @submit=${this.setKey}><label>Provider ID<input name="provider" required .value=${ep.id ?? 'deepseek'}></label><label>API Key<input type="password" name="key" required autocomplete="off"></label><label class="sx-check"><input name="persist" type="checkbox" checked> 保存到 .env（持久化）</label><button ?disabled=${this.busy}>设置凭据</button></form>
      ${this.keyNotice?html`<p class="sx-muted">${this.keyNotice}</p>`:nothing}${this.models.credentials.map((c:any)=>html`<p class="sx-muted">${c.provider} · ${c.status==='ok'?'已配置':'未配置'} ${c.masked}</p>`)}</details>
      <form @submit=${this.saveConfig}>
        <label>模型 ID（用户填写，格式 provider/model）<input name="model" required placeholder="deepseek/deepseek-flash" .value=${`${this.config.defaults.provider ?? ''}/${this.config.defaults.model ?? ''}`}></label>
        <div class="sx-grid2"><label>思考强度<select name="thinking">${this.models.thinkingLevels.map((l:string)=>html`<option ?selected=${l===this.config.defaults.thinkingLevel}>${l}</option>`)}</select></label>
        <label>并行任务<input name="concurrency" type="number" min="1" max="16" .value=${String(this.config.concurrency ?? 3)}></label></div>
        <p class="sx-muted">已取消模型选择与按阶段分档：所有阶段统一使用上面填写的模型，端点与参数在下方配置。</p>
        <label class="sx-check"><input name="strict" type="checkbox" ?checked=${this.config.strict}> 严格质量检查</label><button class="sx-primary" ?disabled=${this.busy}>保存设置</button>
      </form>
      <details open><summary>模型端点与参数（全部由你填写）</summary>
        <p class="sx-muted">模型 ID、端点地址、API 类型、上下文长度、最大输出、能力标记与价格都由你填写；保存后写入 models.json 并刷新运行时。</p>
        <form @submit=${this.saveEndpoint}>
          <label>Provider ID<input name="id" required .value=${ep.id ?? 'deepseek'}></label>
          <label>Base URL<input name="baseUrl" type="url" required .value=${ep.baseUrl ?? 'https://api.deepseek.com'}></label>
          <label>API 类型<input name="api" required .value=${ep.api ?? 'openai-completions'}></label>
          <label>密钥环境变量引用<input name="keyEnvVar" required placeholder="$DEEPSEEK_API_KEY" .value=${ep.keyEnvVar ? `$${ep.keyEnvVar}` : '$DEEPSEEK_API_KEY'}></label>
          <label>模型 ID（逗号分隔）<input name="models" required .value=${(ep.models ?? []).join(', ') || 'deepseek-flash'}></label>
          <div class="sx-grid2"><label>Context Window<input name="contextWindow" type="number" min="1" .value=${String(ep.contextWindow ?? 1000000)}></label>
          <label>Max Tokens<input name="maxTokens" type="number" min="1" .value=${String(ep.maxTokens ?? 32768)}></label></div>
          <label class="sx-check"><input name="reasoning" type="checkbox" ?checked=${ep.reasoning ?? true}> 支持 thinking</label>
          <label class="sx-check"><input name="vision" type="checkbox" ?checked=${ep.vision ?? true}> 支持图片输入</label>
          <div class="sx-grid2"><label>输入价格 / 1M tokens<input name="costInput" type="number" step="0.001" min="0" .value=${String(ep.cost?.input ?? 0)}></label>
          <label>输出价格 / 1M tokens<input name="costOutput" type="number" step="0.001" min="0" .value=${String(ep.cost?.output ?? 0)}></label></div>
          <button ?disabled=${this.busy}>保存模型端点与参数</button>
        </form>
        ${this.endpointNotice ? html`<p class="sx-muted">${this.endpointNotice}</p>` : nothing}
      </details>
      <details><summary>MCP 搜索服务</summary>
        <p class="sx-muted">配置 MCP server（stdio / HTTP）来提供联网检索。是否需要 API key 由该 server 决定；SolveX 只转发，不代管密钥，配置里一律写成 $VAR 引用，并在启动服务前用 export 设置好环境变量。</p>
        <ul class="sx-mcp-list">${(this.mcp?.servers ?? []).map((s:any)=>html`<li><span class="sx-dot ${s.state==='connected'?'completed':s.state==='failed'?'failed':''}"></span><strong>${s.name}</strong> · ${s.state} · ${s.tools.length} 个工具${s.error?html`<small>${s.error}</small>`:nothing}${s.missingEnv?.length?html`<small class="sx-mcp-warn">缺少环境变量：${s.missingEnv.join('、')}（该 server 的 API key 可能没设）</small>`:nothing}</li>`)}
          ${this.mcp?.servers?.length?nothing:html`<li class="sx-muted">未配置 MCP 服务，P1 保持离线建模。</li>`}</ul>
        <div class="sx-section-label">常用搜索服务 <span>${this.mcpPresets.length}</span></div>
        <div class="sx-preset-list">${this.mcpPresets.map((p:any)=>html`<div class="sx-preset">
          <div class="sx-preset-head"><strong>${p.name}</strong>${p.requiresKey?html`<span class="sx-preset-tag">需要 key</span>`:html`<span class="sx-preset-tag free">零 key</span>`}${p.enabled?html`<span class="sx-preset-tag on">已启用</span>`:nothing}</div>
          <p>${p.summary}</p>
          ${p.note?html`<p class="sx-muted">${p.note}</p>`:nothing}
          ${p.requiresKey?html`<p class="sx-muted">需 export：${p.envVars.join('、')} ${p.missingEnv?.length?html`<span class="sx-mcp-warn">（当前未设置）</span>`:nothing}</p>`:nothing}
          <div class="sx-preset-actions"><button type="button" ?disabled=${p.enabled||this.busy} @click=${()=>this.enableMcpPreset(p.id)}>${p.enabled?'已启用':'一键启用'}</button><a class="sx-muted" href=${p.docsUrl} target="_blank" rel="noopener noreferrer">官方文档 ↗</a></div>
        </div>`)}</div>
        <form @submit=${this.saveMcp}><label>mcp.json<textarea name="config" rows="8" spellcheck="false" .value=${JSON.stringify(this.mcp?.config ?? { mcpServers: {} }, null, 2)}></textarea></label>
          <div class="sx-grid2"><button class="sx-primary" ?disabled=${this.busy}>保存并重连</button><button type="button" @click=${this.refreshMcp}>重新连接</button></div></form>
        <p class="sx-muted">配置文件：${this.mcp?.path ?? ''} ${this.mcp?.errors?.length?html`<br>校验错误：${this.mcp.errors.join('；')}`:nothing}</p>
      </details>
    </section></div>`;
  }
  render() {
    const w = this.workspace; const running = this.status === 'running';
    const task = this.transcript.get(this.taskId);
    return html`<div class="sx-app">
      <aside class="sx-sidebar"><a class="sx-brand" href="/">Solve<span>X</span><small>数学建模工作区</small></a>
        <form class="sx-new" @submit=${this.createWorkspace}><input name="name" placeholder="新工作区名称" aria-label="新工作区名称" required maxlength="100"><button aria-label="创建工作区" title="创建工作区" ?disabled=${this.busy}>＋</button></form>
        <div class="sx-section-label">工作区 <span>${this.workspaces.length}</span></div>
        <nav aria-label="工作区">${this.workspaces.length ? repeat(this.workspaces,w=>w.id,w=>html`<div class="sx-row"><button class="sx-workspace ${w.id===this.workspace?.id?'active':''}" ?disabled=${this.busy} @click=${()=>this.perform(()=>this.selectWorkspace(w.id))}><span class="sx-folder">▱</span><span>${w.name}<small>${w.files.length} 个文件</small></span></button><button class="sx-del" title="删除工作区" aria-label=${`删除工作区 ${w.name}`} ?disabled=${this.busy} @click=${()=>this.deleteWorkspace(w.id,w.name)}>×</button></div>`) : html`<p class="sx-muted sx-pad">创建一个工作区开始。</p>`}</nav>
        ${w?.runs.length ? html`<div class="sx-section-label">运行记录 <span>${w.runs.length}${hasActiveRuns(w.runs) ? ' · 并行中' : ''}</span></div><nav aria-label="运行记录">${w.runs.map((r,i)=>html`<div class="sx-row"><button class="sx-run ${r.id===this.sessionId?'active':''}" ?disabled=${this.busy} @click=${()=>this.perform(()=>this.selectRun(r))}><span class="sx-dot ${r.status}"></span><span>运行 ${w.runs.length-i}<small>${new Date(r.created_at).toLocaleString('zh-CN')}</small><small class="sx-run-runtime">${runtimeLabel(r)}</small></span></button><button class="sx-del" title="删除运行记录" aria-label=${`删除运行 ${w.runs.length-i}`} ?disabled=${this.busy} @click=${()=>this.deleteRun(r)}>×</button></div>`)}</nav>` : nothing}
        <footer><button @click=${this.openSettings}>⚙ 模型设置</button><button aria-label="切换主题" @click=${()=>{this.theme=this.theme==='light'?'dark':'light';localStorage.setItem('solvex-theme',this.theme);document.documentElement.classList.toggle('dark',this.theme==='dark');this.requestUpdate();}}>◐</button><small>Powered by Pi Web UI</small></footer>
      </aside>
      <div class="sx-body"><header class="sx-topbar"><div><span class="sx-muted">工作区 / </span><strong>${w?.name ?? '开始使用'}</strong></div><div class="sx-actions"><button class="sx-button" @click=${this.openSettings} title="配置模型与 API Key">⚙ 模型设置 / API Key</button>${this.sessionId ? html`<span class="sx-badge ${this.status}"><span class="sx-dot ${this.status}"></span>${labels[this.status] ?? this.status}</span><a class="sx-button" href=${`/api/download/${this.sessionId}`}>下载产物</a>`:nothing}
        ${running ? html`<button class="sx-stop" @click=${this.stopRun}>停止本次运行</button>`:nothing}
        ${this.sessionId && (this.status==='aborted'||this.status==='failed') ? html`<button class="sx-button" ?disabled=${this.busy} @click=${this.resumeRun} title="已完成的步骤从会话日志回放，中断的步骤接着跑，不重复调用模型">从断点续跑</button>`:nothing}
        <button class="sx-primary" ?disabled=${!canStartNewRun(w)||this.busy} @click=${this.start} title="每次点击都会新建一个独立运行">${this.busy?'处理中…':'新建运行'} <span>↗</span></button></div></header>
        ${this.error ? html`<div class="sx-error" role="alert">${this.error}<button aria-label="关闭错误" @click=${()=>{this.error='';this.requestUpdate();}}>×</button></div>`:nothing}
        <div class="sx-content"><main class="sx-main">
          ${!w ? html`<section class="sx-welcome"><div class="sx-monogram">X</div><p class="sx-eyebrow">FROM PROBLEM TO PAPER</p><h1>让题目成为起点。</h1><p>创建工作区，上传数学建模题目。<br>建模、编程、验证与论文，自动衔接。</p><p class="sx-muted">从左侧创建第一个工作区。</p></section>` : !this.sessionId ? html`<section class="sx-welcome"><div class="sx-monogram">▤</div><p class="sx-eyebrow">${w.files.length?'READY WHEN YOU ARE':'YOUR MODELING WORKSPACE'}</p><h1>${w.problemFilename?'题目已就绪。':'从一道题目开始。'}</h1><p>${w.problemFilename ?? '上传题目和数据附件，剩下的交给 SolveX。'}</p>
            <label class="sx-drop" @dragover=${(e:DragEvent)=>e.preventDefault()} @drop=${(e:DragEvent)=>{e.preventDefault();if(!this.busy)void this.upload(Array.from(e.dataTransfer?.files??[]));}}><span class="sx-upload-icon">↑</span><strong>${this.busy?'正在解析文件…':'拖入文件，或点击上传'}</strong><span>题目：PDF、DOCX、MD、TXT · 数据附件可一并上传</span><small>单个文件最多 50 MB · 每次最多 30 个</small><input type="file" multiple aria-label="上传题目与附件" ?disabled=${this.busy} @change=${(e:Event)=>{const el=e.currentTarget as HTMLInputElement;void this.upload(Array.from(el.files??[]));el.value='';}}></label>
            <div class="sx-flow"><span>01 建模</span><span>02 编程与审查</span><span>03 图表</span><span>04 论文</span></div></section>` : html`
              <div class="sx-transcript-heading"><div><p class="sx-eyebrow">LIVE WORKFLOW</p><h1>${this.stages.get(this.taskId)?.label ?? this.taskId}</h1></div><span class="sx-muted">${this.usage.tokens.toLocaleString()} tokens · $${this.usage.cost.toFixed(3)}</span></div>
              <p class="sx-runtime-note">本次运行配置：${runtimeLabel(findRun(w?.runs, this.sessionId))}</p>
              <div class="sx-stage-tabs" role="group" aria-label="运行阶段">${[...this.stages.values()].map(s=>html`<button class=${s.id===this.taskId?'active':''} @click=${()=>{this.taskId=s.taskId??s.id;this.requestUpdate();}}><span class="sx-dot ${s.state}"></span>${s.label || s.id}</button>`)}</div>
              <div class="sx-transcript"><message-list .messages=${task.messages.map(m=>('content' in m ? {...m,content:Array.isArray(m.content)?m.content.map(c=>({...c})):m.content} : {...m}))} .pendingToolCalls=${new Set(task.pending)} .isStreaming=${false}></message-list>${task.messages.length?nothing:html`<p class="sx-muted">${running?'等待此阶段开始…':'此阶段没有消息记录。'}</p>`}</div>
              <div class="sx-activity" role="status"><span class="sx-dot ${this.status}"></span>${running ? this.activity : labels[this.status] ?? this.status}</div>`}
        </main>
        ${w ? html`<aside class="sx-files"><header><h2>工作区文件</h2><label class="sx-add" title="上传文件">＋<input type="file" multiple aria-label="添加工作区文件" ?disabled=${this.busy} @change=${(e:Event)=>{const el=e.currentTarget as HTMLInputElement;void this.upload(Array.from(el.files??[]));el.value='';}}></label></header>
          <div class="sx-section-label">输入文件 <span>${w.files.length}</span></div>
          <div class="sx-file-list">${w.files.length ? w.files.map(f=>html`<div class="sx-file"><span class="sx-file-icon">▤</span><div><strong title=${f.filename}>${f.filename}</strong><small>${bytes(f.size)} ${w.problemFilename===f.filename?'· 主问题':''}</small></div>${f.problemReady?html`<input type="radio" name="main-problem" title="设为主题目" aria-label=${`将 ${f.filename} 设为主题目`} ?checked=${w.problemFilename===f.filename} ?disabled=${this.busy||running} @change=${()=>this.chooseProblem(f.filename)}>`:nothing}</div>`):html`<p class="sx-muted sx-pad">题目与附件将在这里保存。</p>`}</div>
          ${w.files.length?html`<p class="sx-hint">选择圆点指定主题目，其余文件作为附件。</p>`:nothing}
          <div class="sx-section-label">运行产物 <span>${this.artifacts.length}</span></div>
          <div class="sx-file-list">${this.artifacts.filter(f=>!f.path.startsWith('data/')&&!f.path.startsWith('00_problem/')).map(f=>html`<button class="sx-artifact" title=${f.path} @click=${()=>this.openArtifact(f)}><span>▤</span><span>${f.path.split('/').pop()}<small>${f.path.split('/').slice(0,-1).join('/')} · ${bytes(f.size)}</small></span></button>`)}</div>
        </aside>`:nothing}</div>
      </div>
      ${this.preview?html`<div class="sx-overlay"><section class="sx-preview" role="dialog" aria-modal="true" aria-label="文件预览"><header><strong>${this.preview.path}</strong><button aria-label="关闭预览" @click=${()=>{this.preview=undefined;this.requestUpdate();}}>×</button></header>${this.preview.kind === 'image' ? html`<img class="sx-image-preview" src=${this.artifactUrl(this.preview.path)} alt=${this.preview.path}>` : this.preview.kind === 'pdf' ? html`<iframe class="sx-pdf-preview" src=${this.artifactUrl(this.preview.path)} title="PDF 预览"></iframe>` : html`<pre>${this.preview.text}</pre>`}</section></div>`:nothing}
      ${this.settingsView()}
    </div>`;
  }
}
customElements.define('solvex-app', SolveXApp);
