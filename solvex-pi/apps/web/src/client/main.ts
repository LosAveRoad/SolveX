import { LitElement, html, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
// These imports register the actual upstream Pi components and tool renderers.
import { MessageList, loadAttachment } from '@earendil-works/pi-web-ui';
import '@earendil-works/pi-web-ui/app.css';
import { GlobalWorkerOptions } from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import type { SolveXEvent, StageNode } from '@solvex/core';
import { TranscriptAdapter } from './transcript.js';
import './style.css';

// Keep Pi's PDF extraction entirely local, including its worker.
GlobalWorkerOptions.workerSrc = pdfWorker;
void MessageList;
type Run = { id: string; status: string; created_at: string };
type Workspace = { id: string; name: string; problemFilename?: string; files: { filename: string; size: number; problemReady: boolean }[]; runs: Run[] };
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
  private error = '';
  private settings = false;
  private models: any;
  private config: any;
  private theme = localStorage.getItem('solvex-theme') || 'light';
  private refreshTimer?: ReturnType<typeof setInterval>;
  private loadVersion = 0;
  protected createRenderRoot() { return this; }
  async connectedCallback() {
    super.connectedCallback(); document.documentElement.classList.toggle('dark', this.theme === 'dark');
    await this.perform(async () => {
      this.workspaces = await api('/api/workspaces');
      const saved = localStorage.getItem('solvex-workspace');
      const selected = this.workspaces.find(w => w.id === saved) ?? this.workspaces[0];
      if (selected) await this.selectWorkspace(selected.id);
    });
    this.refreshTimer = setInterval(() => { if (this.status === 'running') void this.refreshArtifacts(); }, 2500);
  }
  disconnectedCallback() { super.disconnectedCallback(); this.source?.close(); clearInterval(this.refreshTimer); }
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
  }
  private async createWorkspace(e: SubmitEvent) {
    e.preventDefault(); const form = e.currentTarget as HTMLFormElement;
    const name = String(new FormData(form).get('name') ?? '');
    await this.perform(async () => {
      const w = await api<Workspace>('/api/workspaces', post({ name }));
      this.workspaces = [w, ...this.workspaces]; form.reset(); await this.selectWorkspace(w.id);
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
  private async start() {
    await this.perform(async () => {
      const w = this.workspace!;
      const { session_id } = await api(`/api/workspaces/${w.id}/run`, post());
      await this.selectRun({id:session_id, status:'running', created_at:new Date().toISOString()});
      this.workspace = await api(`/api/workspaces/${w.id}`);
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
      this.models = await api('/api/models'); this.config = structuredClone(this.models.config); this.settings = true;
    });
  }
  private async saveConfig(e: SubmitEvent) {
    e.preventDefault(); const data = new FormData(e.currentTarget as HTMLFormElement);
    await this.perform(async () => {
      const [provider, ...modelParts] = String(data.get('model') ?? '').split('/');
      const selectedModel = this.models.models.find((m:any) => `${m.provider}/${m.id}` === data.get('model'));
      const defaults = { provider:provider || '', model:modelParts.join('/') || '', thinkingLevel:selectedModel && !selectedModel.reasoning ? 'off' : data.get('thinking') };
      const byPhase = { ...this.config.byPhase };
      for (const phase of ['P1', 'P2_IMPL', 'P2_REVIEW', 'P4']) {
        const choice = String(data.get(phase) ?? '');
        if (choice) { const [provider, ...parts] = choice.split('/'); const m = this.models.models.find((m:any)=>`${m.provider}/${m.id}`===choice); byPhase[phase] = { provider, model:parts.join('/'), thinkingLevel:m && !m.reasoning ? 'off' : defaults.thinkingLevel }; }
        else byPhase[phase] = { provider:'', model:'', thinkingLevel:defaults.thinkingLevel };
      }
      await api('/api/models/config', {method:'PUT', body:JSON.stringify({ defaults, byPhase,
        concurrency:Number(data.get('concurrency')), strict:data.get('strict') === 'on' })});
      this.settings = false;
    });
  }
  private async setKey(e: SubmitEvent) {
    e.preventDefault(); const form = e.currentTarget as HTMLFormElement; const data = new FormData(form);
    await this.perform(async () => { await api('/api/models/api-key', post({provider:data.get('provider'), apiKey:data.get('key')})); form.reset(); this.models = await api('/api/models'); });
  }
  private settingsView() {
    if (!this.settings || !this.models) return nothing;
    const choices = (selected: string, inherit = false) => html`${html`<option value="">${inherit?'使用默认模型':'使用服务端默认模型'}</option>`}${this.models.models.map((m:any) => html`<option value=${`${m.provider}/${m.id}`} ?selected=${selected === `${m.provider}/${m.id}`}>${m.provider} / ${m.name ?? m.id}</option>`)}`;
    return html`<div class="sx-overlay" @click=${(e:Event) => { if(e.target===e.currentTarget) {this.settings=false;this.requestUpdate();} }}><section class="sx-dialog" role="dialog" aria-modal="true" aria-label="模型设置">
      <header><h2>模型与运行设置</h2><button aria-label="关闭设置" @click=${()=>{this.settings=false;this.requestUpdate();}}>×</button></header>
      <form @submit=${this.saveConfig}>
        <label>默认模型<select name="model">${choices(`${this.config.defaults.provider}/${this.config.defaults.model}`)}</select></label>
        <div class="sx-grid2"><label>思考强度<select name="thinking">${this.models.thinkingLevels.map((l:string)=>html`<option ?selected=${l===this.config.defaults.thinkingLevel}>${l}</option>`)}</select></label>
        <label>并行任务<input name="concurrency" type="number" min="1" max="16" .value=${String(this.config.concurrency ?? 3)}></label></div>
        <details><summary>按阶段选择模型</summary>${[['P1','建模'],['P2_IMPL','编程'],['P2_REVIEW','审查'],['P4','论文']].map(([phase,name])=>html`<label>${name}<select name=${phase}>${choices(this.config.byPhase?.[phase] ? `${this.config.byPhase[phase].provider}/${this.config.byPhase[phase].model}` : '',true)}</select></label>`)}</details>
        <label class="sx-check"><input name="strict" type="checkbox" ?checked=${this.config.strict}> 严格质量检查</label><button class="sx-primary" ?disabled=${this.busy}>保存设置</button>
      </form>
      <details><summary>模型凭据</summary><p class="sx-muted">API Key 仅用于当前服务进程。</p><form @submit=${this.setKey}><label>Provider<select name="provider">${[...new Set(this.models.models.map((m:any)=>m.provider))].map(p=>html`<option>${p}</option>`)}</select></label><label>API Key<input type="password" name="key" required autocomplete="off"></label><button ?disabled=${this.busy}>设置凭据</button></form>
      ${this.models.credentials.map((c:any)=>html`<p class="sx-muted">${c.provider} · ${c.status==='ok'?'已配置':'未配置'} ${c.masked}</p>`)}</details>
      <details><summary>自定义 OpenAI 兼容端点</summary><form @submit=${(e:SubmitEvent)=>{e.preventDefault();const d=new FormData(e.currentTarget as HTMLFormElement);void this.perform(async()=>{await api('/api/models/endpoints',{method:'PUT',body:JSON.stringify({id:d.get('provider'),baseUrl:d.get('url'),api:'openai-completions',apiKey:d.get('key'),models:String(d.get('models')).split(',').map(x=>x.trim()).filter(Boolean)})});this.models=await api('/api/models');});}}><label>Provider ID<input name="provider" required></label><label>Base URL<input name="url" type="url" required placeholder="https://example.com/v1"></label><label>密钥环境变量引用<input name="key" pattern=${String.raw`\$[A-Za-z_][A-Za-z0-9_]*`} placeholder="$MY_API_KEY" required></label><label>模型 ID（逗号分隔）<input name="models" required></label><button ?disabled=${this.busy}>保存端点</button></form></details>
    </section></div>`;
  }
  render() {
    const w = this.workspace; const running = this.status === 'running';
    const task = this.transcript.get(this.taskId);
    return html`<div class="sx-app">
      <aside class="sx-sidebar"><a class="sx-brand" href="/">Solve<span>X</span><small>数学建模工作区</small></a>
        <form class="sx-new" @submit=${this.createWorkspace}><input name="name" placeholder="新工作区名称" aria-label="新工作区名称" required maxlength="100"><button aria-label="创建工作区" title="创建工作区" ?disabled=${this.busy}>＋</button></form>
        <div class="sx-section-label">工作区 <span>${this.workspaces.length}</span></div>
        <nav aria-label="工作区">${this.workspaces.length ? repeat(this.workspaces,w=>w.id,w=>html`<button class="sx-workspace ${w.id===this.workspace?.id?'active':''}" ?disabled=${this.busy} @click=${()=>this.perform(()=>this.selectWorkspace(w.id))}><span class="sx-folder">▱</span><span>${w.name}<small>${w.files.length} 个文件</small></span></button>`) : html`<p class="sx-muted sx-pad">创建一个工作区开始。</p>`}</nav>
        ${w?.runs.length ? html`<div class="sx-section-label">运行记录</div><nav aria-label="运行记录">${w.runs.map((r,i)=>html`<button class="sx-run ${r.id===this.sessionId?'active':''}" ?disabled=${this.busy} @click=${()=>this.perform(()=>this.selectRun(r))}><span class="sx-dot ${r.status}"></span><span>运行 ${w.runs.length-i}<small>${new Date(r.created_at).toLocaleString('zh-CN')}</small></span></button>`)}</nav>` : nothing}
        <footer><button @click=${this.openSettings}>⚙ 模型设置</button><button aria-label="切换主题" @click=${()=>{this.theme=this.theme==='light'?'dark':'light';localStorage.setItem('solvex-theme',this.theme);document.documentElement.classList.toggle('dark',this.theme==='dark');this.requestUpdate();}}>◐</button><small>Powered by Pi Web UI</small></footer>
      </aside>
      <div class="sx-body"><header class="sx-topbar"><div><span class="sx-muted">工作区 / </span><strong>${w?.name ?? '开始使用'}</strong></div><div class="sx-actions">${this.sessionId ? html`<span class="sx-badge ${this.status}"><span class="sx-dot ${this.status}"></span>${labels[this.status] ?? this.status}</span><a class="sx-button" href=${`/api/download/${this.sessionId}`}>下载产物</a>`:nothing}
        ${running ? html`<button class="sx-stop" @click=${()=>this.perform(async()=>{await api(`/api/abort/${this.sessionId}`,post());this.status='aborted';this.source?.close();await this.refreshArtifacts();})}>停止运行</button>`:html`<button class="sx-primary" ?disabled=${!w?.problemFilename||this.busy} @click=${this.start}>${this.busy?'处理中…':'开始建模'} <span>↗</span></button>`}</div></header>
        ${this.error ? html`<div class="sx-error" role="alert">${this.error}<button aria-label="关闭错误" @click=${()=>{this.error='';this.requestUpdate();}}>×</button></div>`:nothing}
        <div class="sx-content"><main class="sx-main">
          ${!w ? html`<section class="sx-welcome"><div class="sx-monogram">X</div><p class="sx-eyebrow">FROM PROBLEM TO PAPER</p><h1>让题目成为起点。</h1><p>创建工作区，上传数学建模题目。<br>建模、编程、验证与论文，自动衔接。</p><p class="sx-muted">从左侧创建第一个工作区。</p></section>` : !this.sessionId ? html`<section class="sx-welcome"><div class="sx-monogram">▤</div><p class="sx-eyebrow">${w.files.length?'READY WHEN YOU ARE':'YOUR MODELING WORKSPACE'}</p><h1>${w.problemFilename?'题目已就绪。':'从一道题目开始。'}</h1><p>${w.problemFilename ?? '上传题目和数据附件，剩下的交给 SolveX。'}</p>
            <label class="sx-drop" @dragover=${(e:DragEvent)=>e.preventDefault()} @drop=${(e:DragEvent)=>{e.preventDefault();if(!this.busy)void this.upload(Array.from(e.dataTransfer?.files??[]));}}><span class="sx-upload-icon">↑</span><strong>${this.busy?'正在解析文件…':'拖入文件，或点击上传'}</strong><span>题目：PDF、DOCX、MD、TXT · 数据附件可一并上传</span><small>单个文件最多 50 MB · 每次最多 30 个</small><input type="file" multiple aria-label="上传题目与附件" ?disabled=${this.busy} @change=${(e:Event)=>{const el=e.currentTarget as HTMLInputElement;void this.upload(Array.from(el.files??[]));el.value='';}}></label>
            <div class="sx-flow"><span>01 建模</span><span>02 编程与审查</span><span>03 图表</span><span>04 论文</span></div></section>` : html`
              <div class="sx-transcript-heading"><div><p class="sx-eyebrow">LIVE WORKFLOW</p><h1>${this.stages.get(this.taskId)?.label ?? this.taskId}</h1></div><span class="sx-muted">${this.usage.tokens.toLocaleString()} tokens · $${this.usage.cost.toFixed(3)}</span></div>
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
