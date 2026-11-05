import type { Issue, StageNode } from "../events/types.js";

export type FlowState = {
  nodes: Map<string, StageNode>;
  issues: Issue[];
  usageByTask: Record<string, { input: number; output: number; cost: number }>;
  models: { name: string; dir: string; verdict: string; issues: Issue[] }[];
  startedAt: number;
};

export function initialState(): FlowState {
  return { nodes: new Map(), issues: [], usageByTask: {}, models: [], startedAt: Date.now() };
}

export function upsertNode(state: FlowState, node: StageNode): void {
  const prev = state.nodes.get(node.id);
  state.nodes.set(node.id, { ...prev, ...node });
}
