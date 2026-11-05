import type { Role, Phase, SolveXEvent, ThinkingLevel, Usage } from "../events/types.js";

export type ModelRef = { provider: string; id: string };

/** 编排层唯一依赖（设计文档 §4.3）。core 完全不 import 任何 Pi 符号。 */
export type RunRequest = {
  role: Role;
  systemPrompt: string;
  task: string;
  cwd: string;
  tools?: string[];
  maxTurns?: number;
  timeoutMs?: number;
  taskId?: string;
  phase?: Phase;
  model?: ModelRef;
  thinkingLevel?: ThinkingLevel;
  scopedModels?: string[];
  /** 并行写安全（R11）：本次会话允许写入的路径前缀。 */
  writablePrefixes?: string[];
  onEvent?: (e: SolveXEvent) => void;
};

export type RunResult = {
  text: string;
  artifacts: string[];
  usage: Usage;
  settled: boolean;
};

export interface AgentRunner {
  run(req: RunRequest, signal?: AbortSignal): Promise<RunResult>;
}

export const DEFAULT_MAX_TURNS: Record<Role, number> = {
  modeling: 25, programming: 30, review: 20, writing: 40, visualization: 25,
};
