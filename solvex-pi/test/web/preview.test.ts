import { it, expect } from 'vitest';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from '@solvex/web';
import { testPaths, startRun, waitForCompletion } from './helpers.js';
it('serves figure previews as their original image bytes and generated HTML as inert text', async () => {
 const paths=testPaths(); const app=await createServer({fake:true,...paths});
 try {
  const {id}=await startRun(app); await waitForCompletion(app,id);
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aOrsAAAAASUVORK5CYII=','base64');
  writeFileSync(join(paths.sessionRoot,id,'04_paper/chart.png'),png);
  writeFileSync(join(paths.sessionRoot,id,'04_paper/report.html'),'<script>alert(1)</script>');
  const image=await app.inject(`/api/artifacts/${id}/04_paper/chart.png`);
  expect(image.headers['content-type']).toContain('image/png'); expect(image.rawPayload).toEqual(png);
  const html=await app.inject(`/api/artifacts/${id}/04_paper/report.html`);
  expect(html.headers['content-type']).toContain('text/plain');
 } finally {await app.close();}
});
