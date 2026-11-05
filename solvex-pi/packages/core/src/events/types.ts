/** SolveX v1.1 事件契约 —— 编排层（core）与 Pi 适配层、WebUI 的唯一数据协议。
 *  设计文档 §4.6；外层 stage/barrier 由 core 权威发出，内层 thinking/output/tool/turn/usage
 *  由 eventBridge 转发 Pi 原生事件，二者靠 taskId 关联（ADR-14）。
 */
export type Phase = 1 | 2 | 3 | 4;
export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";
export type TaskId = string; // "P1" | "P2-IMPL:model_2" | "P2-REVIEW:model_2" | ...
export type Role = "modeling" | "programming" | "writing" | "visualization" | "review";

export const THINKING_LEVELS: readonly ThinkingLevel[] =
  ["off", "minimal", "low", "medium", "high", "xhigh", "max"] as const;

export type Issue = {
  code: string;
  severity: "critical" | "warn";
  evidence?: string;
  model?: string;
};

export type Usage = { input: number; output: number; cost?: number };
export type UsageDetail = {
  input: number; output: number; cacheRead: number; cacheWrite: number;
  totalTokens: number; cost: number;
};

/** 运行阶段 DAG 节点（右栏时间线数据模型，§10.5.3） */
export type StageNode = {
  id: string; label: string; phase: Phase; kind: "stage" | "task";
  state: "pending" | "queued" | "running" | "done" | "failed" | "aborted" | "skipped";
  parentId?: string; dependsOn: string[]; taskId?: TaskId; model?: string;
  role?: Role; startedAt?: number; endedAt?: number; turns?: number; toolCalls?: number;
  usage?: Usage; thinkingMs?: number;
  verdict?: "satisfied" | "needs_revision" | "unknown"; issues?: Issue[];
};

export type RunSummary = {
  sessionId: string;
  status: "running" | "completed" | "failed" | "aborted";
  models: { name: string; dir: string; verdict: string; issues: Issue[] }[];
  usageByTask: Record<string, Usage>;
  issues: Issue[];
  elapsedMs: number;
  totalTokens?: number;
  totalCost?: number;
};

export type SolveXEvent =
  // ── 兼容旧版（CLI 彩色渲染不变）──
  | { type: "status" | "step" | "done" | "info" | "warn"; message: string;
      phase: Phase; model?: string; taskId?: TaskId; ts: number }
  | { type: "artifact"; path: string; phase: Phase; model?: string; taskId?: TaskId; ts?: number }
  | { type: "complete"; result: RunSummary; ts?: number }
  | { type: "error"; message: string; phase?: Phase; taskId?: TaskId; ts?: number }
  // ── 运行阶段（外层，core 权威发出）──
  | { type: "stage"; op: "upsert" | "remove"; node: StageNode; ts: number }
  | { type: "barrier"; id: string; state: "waiting" | "released";
      completed: number; total: number; ts: number }
  // ── 思考 / 输出 / 工具（内层，eventBridge 转发 Pi 事件）──
  | { type: "thinking"; state: "start" | "delta" | "end"; taskId: TaskId;
      blockId: string; contentIndex: number; delta?: string;
      content?: string; redacted?: boolean; ts: number }
  | { type: "output"; state: "delta" | "end" | "final"; taskId: TaskId;
      blockId: string; contentIndex: number; delta?: string;
      content?: string; message?: unknown; ts: number }
  | { type: "tool"; taskId: TaskId; toolCallId: string; name: string;
      state: "start" | "update" | "delta" | "end"; args?: unknown;
      partialResult?: unknown; result?: unknown; isError?: boolean;
      durationMs?: number; ts: number }
  | { type: "turn"; taskId: TaskId; state: "start" | "end"; turn: number; ts: number }
  // ── 模型 / 用量 / 生命周期 ──
  | { type: "model"; taskId?: TaskId; provider: string; model: string;
      thinkingLevel?: ThinkingLevel; ts: number }
  | { type: "usage"; taskId?: TaskId; input: number; output: number;
      cacheRead: number; cacheWrite: number; totalTokens: number;
      cost: number; cumulative: boolean; ts: number }
  | { type: "lifecycle"; taskId: TaskId;
      state: "agent_start" | "agent_end" | "agent_settled" | "compaction" | "auto_retry" | "aborted";
      detail?: string; ts: number }
  | { type: "ping"; ts: number };

export const SOLVEX_EVENT_TYPES: readonly SolveXEvent["type"][] = [
  "status", "step", "done", "info", "warn", "artifact", "complete", "error",
  "stage", "barrier", "thinking", "output", "tool", "turn", "model", "usage",
  "lifecycle", "ping",
] as const;

/** 事件类型守卫（Web store reducer 用） */
export function isSolveXEvent(v: unknown): v is SolveXEvent {
  return !!v && typeof v === "object" && typeof (v as any).type === "string"
    && (SOLVEX_EVENT_TYPES as readonly string[]).includes((v as any).type);
}
