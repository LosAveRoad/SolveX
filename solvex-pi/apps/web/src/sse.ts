import type { FastifyInstance } from "fastify";
import type { SessionRegistry } from "./runner.js";
import type { SolveXEvent } from "@solvex/core";

/** 单条 SSE 通道承载全部 SolveXEvent；event:=type，id:=自增序号 → Last-Event-ID 续传。 */
export function registerSse(app: FastifyInstance, registry: SessionRegistry, pingMs = 30_000): void {
  app.get("/api/stream/:id", async (req, reply) => {
    const id = (req.params as any).id as string;
    const s = registry.get(id);
    if (!s) return reply.code(404).send({ error: "session not found" });

    reply.hijack();
    const raw = reply.raw;
    raw.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });
    const write = (seq: number, e: SolveXEvent) => {
      if (raw.writableEnded || raw.destroyed) return;
      raw.write(`id: ${seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`);
    };

    const lastId = Number((req.headers as any)["last-event-id"] ?? 0);
    let off: () => void = () => {};
    let timer: ReturnType<typeof setInterval>;
    const close = () => { off(); clearInterval(timer); if (!raw.writableEnded) raw.end(); };
    const isTerminal = (e: { type: string }) => e.type === "complete" || e.type === "error";

    // 首事件 status
    write(0, { type: "status", message: "stream connected", phase: 1, ts: Date.now() });
    let sawTerminal = false;
    for (const r of s.bus.history(lastId)) {
      write(r.seq, r.event);
      if (isTerminal(r.event)) sawTerminal = true;
    }

    off = s.bus.subscribe((e) => {
      write(s.bus.lastSeq, e);
      if (isTerminal(e)) setTimeout(close, 60);
    });
    timer = setInterval(() => {
      if (!raw.writableEnded && !raw.destroyed)
        raw.write(`id: 0\nevent: ping\ndata: ${JSON.stringify({ type: "ping", ts: Date.now() })}\n\n`);
    }, Math.max(50, pingMs));
    // 运行已结束且终端事件只在历史里时，也要关流（否则刷新回放会挂住连接）
    if (sawTerminal || s.bus.state !== "running") setTimeout(close, 60);

    req.raw.on("close", () => { off(); clearInterval(timer); });
  });
}
