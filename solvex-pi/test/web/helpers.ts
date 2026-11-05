import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export function testPaths() {
  const root = mkdtempSync(join(tmpdir(), "solvex-web-"));
  return { root, sessionRoot: join(root, "sessions"), configPath: join(root, "config.json"),
           modelsPath: join(root, "models.json") };
}

/** 手写标准 multipart body，避免额外依赖；字段名与前端 toFormEntries 一致。 */
export function multipart(fields: Record<string, string> = {},
                          files: { filename: string; content: string }[] = []) {
  const b = "----solvex-test-boundary";
  let body = "";
  for (const [k, v] of Object.entries(fields))
    body += `--${b}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`;
  for (const f of files)
    body += `--${b}\r\nContent-Disposition: form-data; name="files[]"; filename="${f.filename}"\r\n` +
            `Content-Type: application/octet-stream\r\n\r\n${f.content}\r\n`;
  body += `--${b}--\r\n`;
  return { body, contentType: `multipart/form-data; boundary=${b}` };
}

export async function startRun(app: any, text = "Test problem", extra: Record<string, string> = {},
                               files: { filename: string; content: string }[] = []) {
  const { body, contentType } = multipart({ text, ...extra }, files);
  const res = await app.inject({ method: "POST", url: "/api/run", payload: body,
    headers: { "content-type": contentType } });
  return { res, id: res.json().session_id as string };
}

export async function waitForCompletion(app: any, id: string, timeoutMs = 3000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const r = await app.inject({ method: "GET", url: `/api/events/${id}?since=0` });
    const events = r.json().events ?? [];
    if (events.some((e: any) => e.type === "complete" || e.type === "error")) return events;
    await new Promise((r2) => setTimeout(r2, 20));
  }
  return [];
}
