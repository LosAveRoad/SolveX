import { describe, it, expect, afterEach } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from '@solvex/web';
import { testPaths, multipart, startRun, waitForCompletion, installFakeRunner } from './helpers.js';

const apps: Awaited<ReturnType<typeof createServer>>[] = [];
afterEach(async () => { for (const app of apps.splice(0)) await app.close(); });
async function setup() {
  const paths = testPaths();
  installFakeRunner();
  const app = await createServer({ ...paths }); apps.push(app);
  const res = await app.inject({ method: 'POST', url: '/api/workspaces', payload: { name: '2026 数模 A题' } });
  expect(res.statusCode).toBe(201);
  return { app, paths, workspace: res.json() };
}
async function upload(app: any, id: string, files: {filename: string; content: string}[], fields = {}) {
  const mp = multipart(fields, files);
  return app.inject({ method: 'POST', url: `/api/workspaces/${id}/files`, payload: mp.body,
    headers: { 'content-type': mp.contentType } });
}
const runDir = (paths: ReturnType<typeof testPaths>, workspaceId: string, runId: string) =>
  join(paths.workspaceRoot, workspaceId, 'runs', runId);

describe('file-first persistent workspaces', () => {
  it('creates a workspace, uploads a problem without any message and completes a run', async () => {
    const { app, paths, workspace: w } = await setup();
    const up = await upload(app, w.id, [{ filename: 'A题.md', content: '# Optimize a transport network' },
      { filename: 'data.csv', content: 'x,y\n1,2' }]);
    expect(up.statusCode).toBe(200);
    expect(up.json().problemFilename).toBe('A题.md');
    const run = await app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`, payload: {} });
    expect(run.statusCode).toBe(200);
    const id = run.json().session_id;
    const events = await waitForCompletion(app, id);
    expect(events.some((e: any) => e.type === 'complete')).toBe(true);
    // 一次运行 = 工作区内一个独立目录；旧的平铺 sessions/ 不再接收工作区产物
    const dir = runDir(paths, w.id, id);
    expect(readFileSync(join(dir, '00_problem/problem.md'), 'utf8')).toContain('transport network');
    expect(readFileSync(join(dir, 'data/data.csv'), 'utf8')).toContain('1,2');
    expect(existsSync(join(dir, 'runtime.json'))).toBe(true);
    expect(existsSync(join(paths.sessionRoot, id))).toBe(false);
    const detail = (await app.inject(`/api/workspaces/${w.id}`)).json();
    expect(detail.runs[0].id).toBe(id);
    expect(detail.runs[0].status).toBe('completed');
    // A new server recovers both files and run associations from disk.
    const restart = await createServer({ ...paths }); apps.push(restart);
    const restored = (await restart.inject(`/api/workspaces/${w.id}`)).json();
    expect(restored.files).toHaveLength(2);
    expect(restored.runs[0].id).toBe(id);
    expect(restored.runs[0].status).toBe('completed');
  });

  it('stores original PDF bytes and uses extracted problem text instead of decoding binary', async () => {
    const { app, paths, workspace: w } = await setup();
    const res = await upload(app, w.id, [{ filename: 'problem.pdf', content: '%PDF-1.7 binary' }],
      { extractedTexts: JSON.stringify({ 'problem.pdf': 'Find the optimal scheduling strategy.' }) });
    expect(res.statusCode).toBe(200);
    const run = await app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`, payload: {} });
    expect(run.statusCode).toBe(200);
    const dir = runDir(paths, w.id, run.json().session_id);
    expect(readFileSync(join(dir, '00_problem/problem.md'), 'utf8')).toBe('Find the optimal scheduling strategy.');
    expect(readFileSync(join(dir, 'data/problem.pdf'), 'utf8')).toBe('%PDF-1.7 binary');
  });

  it('rejects missing or empty problem documents and lets a user select the main document', async () => {
    const { app, workspace: w } = await setup();
    expect((await app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`, payload: {} })).statusCode).toBe(400);
    await upload(app, w.id, [{ filename: 'empty.txt', content: '  ' }, { filename: 'data.csv', content: '1,2' }]);
    expect((await app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`, payload: {} })).statusCode).toBe(400);
    await upload(app, w.id, [{ filename: 'one.md', content: 'One' }, { filename: 'two.md', content: 'Two' }]);
    const select = await app.inject({ method: 'PUT', url: `/api/workspaces/${w.id}/problem`, payload: { filename: 'two.md' } });
    expect(select.statusCode).toBe(200);
    expect(select.json().problemFilename).toBe('two.md');
    expect((await app.inject({ method: 'PUT', url: `/api/workspaces/${w.id}/problem`, payload: { filename: 'data.csv' } })).statusCode).toBe(400);
  });

  it('rejects traversal, duplicate names, invalid workspaces and partial upload writes', async () => {
    const { app, workspace: w } = await setup();
    const bad = await upload(app, w.id, [{ filename: 'ok.md', content: 'A' }, { filename: '..', content: 'evil' }]);
    expect(bad.statusCode).toBe(400);
    expect((await app.inject(`/api/workspaces/${w.id}`)).json().files).toHaveLength(0);
    await upload(app, w.id, [{ filename: 'one.md', content: 'original' }]);
    expect((await upload(app, w.id, [{ filename: 'one.md', content: 'replacement' }])).statusCode).toBe(409);
    expect((await app.inject('/api/workspaces/missing')).statusCode).toBe(404);
    expect((await app.inject({ method: 'POST', url: '/api/workspaces', payload: { name: '   ' } })).statusCode).toBe(400);
  });

  it('runs two independent runtimes in parallel without overwriting each other', async () => {
    const { app, paths, workspace: w } = await setup();
    const runner = installFakeRunner({ delayMs: 30 });
    await upload(app, w.id, [{ filename: 'problem.txt', content: 'Optimize' }]);
    const [a, b] = await Promise.all([
      app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/runs`,
        payload: { runtime: { concurrency: 1, strict: true,
          defaults: { provider: 'openai', model: 'gpt-5', thinkingLevel: 'low' } } } }),
      app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`,
        payload: { runtime: { concurrency: 2, strict: false, apiKey: 'sk-should-not-persist' } } }),
    ]);
    expect([a.statusCode, b.statusCode]).toEqual([200, 200]);
    const first = a.json().session_id, second = b.json().session_id;
    expect(first).not.toBe(second);
    const dirA = runDir(paths, w.id, first), dirB = runDir(paths, w.id, second);
    expect(existsSync(dirA)).toBe(true); expect(existsSync(dirB)).toBe(true);
    const runtimeA = JSON.parse(readFileSync(join(dirA, 'runtime.json'), 'utf8'));
    const runtimeB = JSON.parse(readFileSync(join(dirB, 'runtime.json'), 'utf8'));
    expect(runtimeA.config.concurrency).toBe(1); expect(runtimeA.config.strict).toBe(true);
    expect(runtimeA.config.defaults.model).toBe('gpt-5');
    expect(runtimeB.config.concurrency).toBe(2); expect(runtimeB.config.strict).toBe(false);
    expect(readFileSync(join(dirB, 'runtime.json'), 'utf8')).not.toContain('sk-should-not-persist');
    expect(existsSync(join(dirA, 'events.jsonl'))).toBe(true);
    expect(existsSync(join(dirB, 'events.jsonl'))).toBe(true);
    expect((await app.inject(`/api/workspaces/${w.id}`)).json().runs).toHaveLength(2);
    // 停止其中一个 run 不会触碰另一个
    await app.inject({ method: 'POST', url: `/api/abort/${first}` });
    const detail = (await app.inject(`/api/workspaces/${w.id}`)).json();
    expect(detail.runs.find((r: any) => r.id === first).status).toBe('aborted');
    expect(detail.runs.find((r: any) => r.id === second).status).not.toBe('aborted');
    await waitForCompletion(app, second);
    runner.mockRestore();
  });

  it('exposes run lists, runtime snapshots and ownership checks; keeps the legacy API working', async () => {
    const { app, paths, workspace: w } = await setup();
    await upload(app, w.id, [{ filename: 'p.md', content: 'First problem' }]);
    const first = (await app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/runs`, payload: {} })).json().session_id;
    const other = (await app.inject({ method: 'POST', url: '/api/workspaces', payload: { name: 'Another problem' } })).json();
    const list = (await app.inject(`/api/workspaces/${w.id}/runs`)).json();
    expect(list.map((r: any) => r.id)).toContain(first);
    expect(list[0].runtime).toMatchObject({ concurrency: 3, strict: false });
    const detail = (await app.inject(`/api/workspaces/${w.id}/runs/${first}`)).json();
    expect(detail.runtime.id).toBe(first);
    expect(detail.runtime.workspaceId).toBe(w.id);
    expect(detail.runtime.inputs.problemFilename).toBe('p.md');
    expect((await app.inject(`/api/workspaces/${other.id}/runs/${first}`)).statusCode).toBe(404);
    expect((await app.inject(`/api/runs/${first}/runtime`)).json().config.concurrency).toBe(3);
    // 旧 /api/run 仍写入平铺 sessions/，且能被统一索引找回
    const legacy = await startRun(app, 'Legacy problem');
    expect(existsSync(join(paths.sessionRoot, legacy.id, '00_problem/problem.md'))).toBe(true);
    const sessions = (await app.inject('/api/sessions')).json();
    expect(sessions.map((s: any) => s.id)).toEqual(expect.arrayContaining([first, legacy.id]));
    expect((await app.inject(`/api/workspaces/${w.id}`)).json().runs.map((r: any) => r.id)).not.toContain(legacy.id);
  });
});
