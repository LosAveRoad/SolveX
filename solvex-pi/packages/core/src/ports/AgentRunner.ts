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
  /** 会话日志（Pi 的 JSONL）。一个会话可承载多次调用，call 区分它们（默认 "main"）。
   *  再次运行同一 path + call：已完成 → 回放结果；中断 → 从日志接着跑；
   *  没开始过 → 在该会话末尾发新任务，继承之前的全部上下文。 */
  journal?: { path: string; call?: string };
  /** 显式完成工具（ADR-0015）：注册成本次会话的一个工具，只有它接受了提交，这次调用才算交付。 */
  submit?: SubmitTool;
  onEvent?: (e: SolveXEvent) => void;
};

/**
 * 提交工具（ADR-0015，同 ReAct 的 Finish、SWE-agent 的 submit、Inspect 的 submit()）。
 * check 在模型调用工具时执行：返回 null 表示接受；返回字符串表示拒绝，原文作为工具错误回给模型，
 * 模型在同一轮里补齐后再调用。core 只定义契约，运行时负责把它注册进会话。
 */
export type SubmitTool = {
  name: string;
  description: string;
  /** JSON Schema（type: object）。 */
  parameters: { type: "object"; properties: Record<string, unknown>; required?: string[] };
  check: (args: Record<string, unknown>) => string | null | Promise<string | null>;
};

export type RunResult = {
  text: string;
  artifacts: string[];
  usage: Usage;
  settled: boolean;
  /** 因 maxTurns 上限被截断（不是模型故障）。 */
  turnCapped?: boolean;
  /** 日志里已有完成记录，直接回放，未调用模型。 */
  replayed?: boolean;
  /** 从中断的日志接着跑。 */
  resumed?: boolean;
  /** 提交工具接受的参数（本次调用内最后一次被接受的提交）；没有成功提交则缺省。回放时从日志恢复。 */
  submitted?: Record<string, unknown>;
};

export interface AgentRunner {
  run(req: RunRequest, signal?: AbortSignal): Promise<RunResult>;
}

/** ADR-0014：r4、r5 里实现会话 3/3 每轮都撞 30 轮上限、需要补写摘要；P1 现在还要检查数据、建共享数据集。 */
export const DEFAULT_MAX_TURNS: Record<Role, number> = {
  modeling: 60, programming: 90, review: 50, writing: 100, visualization: 25,
};
