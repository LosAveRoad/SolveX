import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { EventBus, SolveXEvent, WorkspaceInfo } from "@solvex/core";

export const EVENT_LOG = "events.jsonl";
const MAX_BYTES = 8 * 1024 * 1024; // 8MB 轮转上限

/** 事件落盘：SSE 断线/刷新回放的数据源。persistThinking=false 时思考正文不落盘（R12）。 */
export function attachEventLog(ws: WorkspaceInfo, bus: EventBus, persistThinking = false): void {
  const f = join(ws.dir, EVENT_LOG);
  writeFileSync(f, "");
  let seq = 0;
  bus.subscribe((event: SolveXEvent) => {
    seq++;
    let stored: SolveXEvent = event;
    if (!persistThinking && event.type === "thinking") {
      const { delta: _d, content: _c, ...rest } = event as any;
      stored = rest as SolveXEvent;
    }
    try {
      if (existsSync(f) && readFileSync(f).length > MAX_BYTES) {
        // 轮转：保留后半段
        const lines = readFileSync(f, "utf-8").split("\n").filter(Boolean);
        writeFileSync(f, lines.slice(Math.floor(lines.length / 2)).join("\n") + "\n");
      }
      appendFileSync(f, JSON.stringify({ seq, event: stored }) + "\n");
    } catch { /* 日志失败不影响主流程 */ }
  });
}

export function readEvents(ws: WorkspaceInfo, since = 0): { seq: number; event: SolveXEvent }[] {
  const f = join(ws.dir, EVENT_LOG);
  if (!existsSync(f)) return [];
  return readFileSync(f, "utf-8").split("\n").filter(Boolean).flatMap((line) => {
    try { const r = JSON.parse(line); return r.seq > since ? [r] : []; } catch { return []; }
  });
}
