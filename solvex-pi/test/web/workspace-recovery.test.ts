import { it, expect } from 'vitest';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from '@solvex/web';
import { testPaths } from './helpers.js';
it('recovers interrupted workspaces as failed, rather than claiming a completed or live run', async () => {
  const paths = testPaths(); const id = 'old-run';
  mkdirSync(join(paths.sessionRoot,id),{recursive:true});
  writeFileSync(join(paths.sessionRoot,id,'.solvex-meta.json'), JSON.stringify({ id, problem:'A', status:'running',created_at:new Date().toISOString() }));
  const app = await createServer({fake:true,...paths});
  try {
    const sessions = (await app.inject('/api/sessions')).json();
    expect(sessions.find((s:any)=>s.id===id).status).toBe('failed');
  } finally { await app.close(); }
});
