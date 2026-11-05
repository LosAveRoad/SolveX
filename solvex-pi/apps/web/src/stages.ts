import type { EventBus, StageNode } from "@solvex/core";

/** 从历史 stage 事件重放全量 DAG 快照（首屏 / 刷新不丢进度）。 */
export function stageSnapshot(bus: EventBus): StageNode[] {
  const map = new Map<string, StageNode>();
  for (const { event } of bus.history()) {
    if (event.type !== "stage") continue;
    if (event.op === "remove") map.delete(event.node.id);
    else map.set(event.node.id, { ...map.get(event.node.id), ...event.node });
  }
  return [...map.values()];
}

export function barrierSnapshot(bus: EventBus): Record<string, { state: string; completed: number; total: number }> {
  const out: Record<string, { state: string; completed: number; total: number }> = {};
  for (const { event } of bus.history()) {
    if (event.type === "barrier") out[event.id] = { state: event.state,
      completed: event.completed, total: event.total };
  }
  return out;
}
