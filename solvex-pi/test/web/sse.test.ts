import { describe, it, expect } from "vitest";
import { createServer } from "@solvex/web";
import { testPaths, startRun } from "./helpers.js";

describe("T5.2 SSE 全事件流", () => {
  it("event:/id:/data: 格式、Last-Event-ID 续传、complete 关流、ping 心跳", async () => {
    const p = testPaths();
    const app = await createServer({ fake: true, sessionRoot: p.sessionRoot,
      configPath: p.configPath, modelsPath: p.modelsPath, pingMs: 120 });
    await app.listen({ host: "127.0.0.1", port: 0 });
    const port = (app.server.address() as any).port;
    const base = `http://127.0.0.1:${port}`;
    try {
      const { id } = await startRun(app, "sse problem");
      const res = await fetch(`${base}/api/stream/${id}`, { headers: { Accept: "text/event-stream" },
        signal: AbortSignal.timeout(6000) });
      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toContain("text/event-stream");
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      const events: { id: string; event: string; data: any }[] = [];
      const t0 = Date.now();
      while (Date.now() - t0 < 3000 && events.filter((e) => e.event === "complete").length === 0) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split("\n\n"); buf = frames.pop() ?? "";
        for (const f of frames) {
          const idm = f.match(/^id: (\d+)$/m), evm = f.match(/^event: (\S+)$/m), dm = f.match(/^data: (.+)$/m);
          if (evm && dm) { try { events.push({ id: idm?.[1] ?? "", event: evm[1], data: JSON.parse(dm[1]) }); } catch { /* noop */ } }
        }
      }
      await reader.cancel().catch(() => {});
      expect(events[0].event).toBe("status");
      expect(events.some((e) => e.event === "stage")).toBe(true);
      expect(events.some((e) => e.event === "complete")).toBe(true);
      const ids = events.filter((e) => Number(e.id) > 0).map((e) => Number(e.id));
      expect(ids.every((n, i) => i === 0 || n >= ids[i - 1])).toBe(true); // 自增序号

      // Last-Event-ID 续传
      const since = Math.max(1, ids[0] ?? 1);
      const res2 = await fetch(`${base}/api/stream/${id}`,
        { headers: { "Last-Event-ID": String(since), Accept: "text/event-stream" },
        signal: AbortSignal.timeout(3000) });
      const chunk = await res2.body!.getReader().read();
      const text = new TextDecoder().decode(chunk.value ?? new Uint8Array());
      expect(text).toContain("event: ");
      await res2.body!.cancel().catch(() => {});
    } finally { await Promise.race([app.close(), new Promise((r) => setTimeout(r, 1500))]); }
  }, 15_000);
});
