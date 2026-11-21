import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, renameSync, rmSync } from 'node:fs';
import { join, extname } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { RUNS_DIR } from '@solvex/core';
import type { SessionRegistry } from './runner.js';

export type Upload = { filename: string; buffer: Buffer };
type InputFile = { filename: string; size: number; problemReady: boolean };
type Workspace = { id: string; name: string; createdAt: string; problemFilename?: string;
  files: InputFile[]; extractedTexts: Record<string, string> };
class WorkspaceError extends Error {
  constructor(message: string, readonly statusCode = 400) { super(message); }
}
const textTypes = new Set(['.md', '.txt']);
const problemTypes = new Set(['.md', '.txt', '.pdf', '.docx']);
const validId = (id: string) => /^[a-f0-9-]{36}$/.test(id);
function validFilename(name: string) {
  return name.length > 0 && name.length <= 200 && !name.startsWith('.') && !/[/\\\x00-\x1f\x7f]/.test(name);
}

/** Managed directories only: browser paths can never select arbitrary server files. */
export class WorkspaceStore {
  constructor(private readonly root: string) {}
  private path(id: string) {
    if (!validId(id)) throw new WorkspaceError('工作区不存在', 404);
    return join(this.root, id);
  }
  /** 该题目工作区下所有 run 的父目录；每次运行在此创建独立子目录。 */
  runsRoot(id: string) { return join(this.path(id), RUNS_DIR); }
  get(id: string): Workspace {
    const meta = join(this.path(id), 'workspace.json');
    if (!existsSync(meta)) throw new WorkspaceError('工作区不存在', 404);
    return JSON.parse(readFileSync(meta, 'utf8'));
  }
  private save(w: Workspace) {
    const p = join(this.path(w.id), 'workspace.json');
    writeFileSync(p + '.tmp', JSON.stringify(w, null, 2));
    renameSync(p + '.tmp', p);
  }
  create(name: string) {
    if (typeof name !== 'string' || !name.trim() || name.trim().length > 100)
      throw new WorkspaceError('工作区名称须为 1–100 个字符');
    const w: Workspace = { id: randomUUID(), name: name.trim(), createdAt: new Date().toISOString(), files: [], extractedTexts: {} };
    mkdirSync(join(this.path(w.id), 'inputs'), { recursive: true }); this.save(w);
    return w;
  }
  list() {
    if (!existsSync(this.root)) return [];
    return readdirSync(this.root).filter(validId).flatMap(id => {
      try { return [this.get(id)]; } catch { return []; }
    }).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  upload(id: string, files: Upload[], extractions: Record<string, unknown>) {
    const w = this.get(id);
    if (!files.length) throw new WorkspaceError('请选择文件');
    const names = new Set(w.files.map(f => f.filename));
    const prepared = files.map(f => {
      if (!validFilename(f.filename)) throw new WorkspaceError('文件名无效');
      if (names.has(f.filename)) throw new WorkspaceError(`文件已存在：${f.filename}`, 409);
      names.add(f.filename);
      const ext = extname(f.filename).toLowerCase();
      const supplied = Object.hasOwn(extractions, f.filename) ? extractions[f.filename] : '';
      const text = textTypes.has(ext) ? f.buffer.toString('utf8') : typeof supplied === 'string' ? supplied : '';
      if (text.length > 2_000_000) throw new WorkspaceError('题目文本过长');
      return { ...f, text: problemTypes.has(ext) ? text.trim() : '' };
    });
    // Validate the complete batch before writing any files.
    for (const f of prepared) {
      writeFileSync(join(this.path(id), 'inputs', f.filename), f.buffer, { flag: 'wx' });
      w.files.push({ filename: f.filename, size: f.buffer.length, problemReady: !!f.text });
      if (f.text) w.extractedTexts[f.filename] = f.text;
    }
    if (!w.problemFilename) w.problemFilename = w.files.find(f => f.problemReady)?.filename;
    this.save(w); return w;
  }
  selectProblem(id: string, filename: string) {
    const w = this.get(id);
    if (!w.files.some(f => f.filename === filename && f.problemReady))
      throw new WorkspaceError('请选择已解析且非空的 PDF、DOCX、Markdown 或 TXT 题目');
    w.problemFilename = filename; this.save(w); return w;
  }
  /** 删除整个工作区（含 inputs 与所有 runs）；path() 已校验 UUID 且目录必然在托管根内。 */
  remove(id: string): void {
    const dir = this.path(id);
    this.get(id); // 不存在则抛 404
    rmSync(dir, { recursive: true, force: true });
  }
  /** 启动瞬间的工作区输入快照；之后改输入不会回溯影响已有 run。 */
  input(id: string) {
    const w = this.get(id);
    const text = w.problemFilename && w.extractedTexts[w.problemFilename];
    if (!text?.trim()) throw new WorkspaceError('请先上传并选择可读取的题目文件（PDF / DOCX / MD / TXT）');
    return { text, files: w.files.map(f => ({ filename: f.filename,
      buffer: readFileSync(join(this.path(id), 'inputs', f.filename)) })) };
  }
}

export function registerWorkspaceRoutes(app: FastifyInstance, store: WorkspaceStore, registry: SessionRegistry) {
  const view = (w: Workspace) => {
    const { extractedTexts: _, ...metadata } = w;
    return { ...metadata, runs: registry.listRuns(w.id) };
  };

  /** 同一工作区可并行启动多个 run：每个 run 有独立目录、事件流、取消控制器与配置快照。 */
  const startRun = async (req: { params: { id: string }; body: unknown }) => {
    const id = req.params.id;
    const w = store.get(id);
    const input = store.input(id);
    const body = (req.body ?? {}) as Record<string, any>;
    const overrides = body.runtime ?? body.overrides ?? body;
    const s = await registry.create({ ...input, workspaceId: id,
      problemFilename: w.problemFilename, runtimeOverrides: overrides });
    return { session_id: s.id, run_id: s.id, workspace_id: id,
      runtime: s.runtime?.config };
  };

  app.get('/api/workspaces', async () => store.list().map(view));
  app.post('/api/workspaces', async (req, reply) => reply.code(201).send(view(store.create((req.body as any)?.name))));
  app.get<{ Params: { id: string } }>('/api/workspaces/:id', async req => view(store.get(req.params.id)));
  app.get<{ Params: { id: string } }>('/api/workspaces/:id/runs', async req => registry.listRuns(store.get(req.params.id).id));
  app.get<{ Params: { id: string; runId: string } }>('/api/workspaces/:id/runs/:runId', async req => {
    const w = store.get(req.params.id);
    const detail = registry.runDetail(req.params.runId);
    if (!detail || detail.workspaceId !== w.id) throw new WorkspaceError('运行不存在', 404);
    return detail;
  });
  app.post<{ Params: { id: string } }>('/api/workspaces/:id/runs', startRun);
  // 旧路径保留兼容；语义已改为「新建一次运行」，不再阻止并行。
  app.post<{ Params: { id: string } }>('/api/workspaces/:id/run', startRun);
  app.post<{ Params: { id: string } }>('/api/workspaces/:id/files', async (req, reply) => {
    store.get(req.params.id);
    const files: Upload[] = []; let extractedTexts: Record<string, unknown> = {};
    for await (const part of req.parts()) {
      if (part.type === 'file') files.push({ filename: part.filename, buffer: await part.toBuffer() });
      else if (part.fieldname === 'extractedTexts') {
        try { extractedTexts = JSON.parse(String(part.value)); }
        catch { throw new WorkspaceError('文档解析结果无效'); }
        if (!extractedTexts || typeof extractedTexts !== 'object' || Array.isArray(extractedTexts))
          throw new WorkspaceError('文档解析结果无效');
      }
    }
    return view(store.upload(req.params.id, files, extractedTexts));
  });
  app.put<{ Params: { id: string } }>('/api/workspaces/:id/problem', async req =>
    view(store.selectProblem(req.params.id, (req.body as any)?.filename)));

  /** 删除整个工作区（题目、附件与全部运行记录），运行中任务先拦下。 */
  app.delete<{ Params: { id: string } }>('/api/workspaces/:id', async (req, reply) => {
    const id = req.params.id;
    try {
      store.get(id);
      if (!registry.forgetWorkspace(id))
        return reply.code(409).send({ error: '该工作区仍有运行中的任务，请先停止后再删除' });
      store.remove(id);
      return { ok: true, id };
    } catch (e: any) {
      return reply.code(e.statusCode ?? 400).send({ error: e.message });
    }
  });

  /** 删除单次运行；支持新布局与旧平铺 sessions 关联到本工作区的历史 run。 */
  app.delete<{ Params: { id: string; runId: string } }>('/api/workspaces/:id/runs/:runId', async (req, reply) => {
    const { id, runId } = req.params;
    try {
      store.get(id);
      const rec = registry.listRuns(id).find((r) => r.id === runId);
      if (!rec) return reply.code(404).send({ error: '运行不存在' });
      if (rec.status === 'running') return reply.code(409).send({ error: '运行尚未结束，请先停止后再删除' });
      registry.remove(runId);
      return { ok: true, id: runId };
    } catch (e: any) {
      return reply.code(e.statusCode ?? 400).send({ error: e.message });
    }
  });
}
