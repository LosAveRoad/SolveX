import type { Phase, SolveXEvent, RunSummary, TaskId, StageNode } from "./types.js";

export type Listener = (e: SolveXEvent) => void;

/** core 权威事件源：同步通知 + 可回放历史 + 终态标记。 */
export class EventBus {
  private listeners = new Set<Listener>();
  private log: { seq: number; event: SolveXEvent }[] = [];
  private terminal: "complete" | "error" | null = null;
  private seq = 0;

  emit(event: SolveXEvent): void {
    const e = ("ts" in event && (event as any).ts !== undefined) ? event : { ...event, ts: Date.now() } as SolveXEvent;
    const rec = { seq: ++this.seq, event: e };
    this.log.push(rec);
    for (const l of [...this.listeners]) l(e);
  }

  private legacy(type: "status" | "step" | "done" | "info" | "warn", message: string,
                 phase: Phase, model?: string, taskId?: TaskId): void {
    this.emit({ type, message, phase, ...(model ? { model } : {}), ...(taskId ? { taskId } : {}), ts: Date.now() });
  }
  status = (m: string, phase: Phase, taskId?: TaskId) => this.legacy("status", m, phase, undefined, taskId);
  step = (m: string, phase: Phase, taskId?: TaskId) => this.legacy("step", m, phase, undefined, taskId);
  done = (m: string, phase: Phase, taskId?: TaskId) => this.legacy("done", m, phase, undefined, taskId);
  info = (m: string, phase: Phase, taskId?: TaskId) => this.legacy("info", m, phase, undefined, taskId);
  warn = (m: string, phase: Phase, taskId?: TaskId) => this.legacy("warn", m, phase, undefined, taskId);

  stage(node: StageNode, op: "upsert" | "remove" = "upsert"): void {
    this.emit({ type: "stage", op, node, ts: Date.now() });
  }
  barrier(id: string, state: "waiting" | "released", completed: number, total: number): void {
    this.emit({ type: "barrier", id, state, completed, total, ts: Date.now() });
  }
  lifecycle(taskId: TaskId, state: "agent_start" | "agent_end" | "agent_settled" | "compaction" | "auto_retry" | "aborted", detail?: string): void {
    this.emit({ type: "lifecycle", taskId, state, ...(detail ? { detail } : {}), ts: Date.now() });
  }

  subscribe(fn: Listener): () => void { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  history(since = 0): { seq: number; event: SolveXEvent }[] { return this.log.filter((r) => r.seq > since); }
  get lastSeq(): number { return this.seq; }
  get state(): "running" | "complete" | "error" { return this.terminal ?? "running"; }

  complete(result: RunSummary): void { this.terminal = "complete"; this.emit({ type: "complete", result, ts: Date.now() }); }
  error(message: string, phase?: Phase, taskId?: TaskId): void {
    this.terminal = "error";
    this.emit({ type: "error", message, ...(phase ? { phase } : {}), ...(taskId ? { taskId } : {}), ts: Date.now() });
  }
}
