import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from '@solvex/web';
import { SessionRegistry } from '../../apps/web/src/runner.js';
import { FakeAgentRunner } from '@solvex/core';
import { testPaths, multipart, waitForCompletion } from './helpers.js';

const apps: Awaited<ReturnType<typeof createServer>>[] = [];
afterEach(async () => { for (const app of apps.splice(0)) await app.close(); });
async function setup() {
  const paths = testPaths();
  const app = await createServer({ fake: true, ...paths }); apps.push(app);
  const res = await app.inject({ method: 'POST', url: '/api/workspaces', payload: { name: '2026 数模 A题' } });
  expect(res.statusCode).toBe(201);
  return { app, paths, workspace: res.json() };
}
async function upload(app: any, id: string, files: {filename: string; content: string}[], fields = {}) {
  const mp = multipart(fields, files);
  return app.inject({ method: 'POST', url: `/api/workspaces/${id}/files`, payload: mp.body,
    headers: { 'content-type': mp.contentType } });
}

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
    expect(readFileSync(join(paths.sessionRoot, id, '00_problem/problem.md'), 'utf8')).toContain('transport network');
    expect(readFileSync(join(paths.sessionRoot, id, 'data/data.csv'), 'utf8')).toContain('1,2');
    const detail = (await app.inject(`/api/workspaces/${w.id}`)).json();
    expect(detail.runs[0].id).toBe(id);
    expect(detail.runs[0].status).toBe('completed');
    // A new server recovers both files and run associations from disk.
    const restart = await createServer({ fake: true, ...paths }); apps.push(restart);
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
    const dir = join(paths.sessionRoot, run.json().session_id);
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

  it('starts at most one run when two requests race', async () => {
    const runner = vi.spyOn(SessionRegistry.prototype as any, 'runner').mockResolvedValue(new FakeAgentRunner({ delayMs: 30, synthetic: true }));
    const { app, workspace: w } = await setup();
    await upload(app, w.id, [{ filename: 'problem.txt', content: 'Optimize' }]);
    const runs = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: `/api/workspaces/${w.id}/run`, payload: {} })));
    expect(runs.map(r => r.statusCode).sort()).toEqual([200, 409]);
    runner.mockRestore();
  });
});
