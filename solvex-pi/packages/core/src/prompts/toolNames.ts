import type { Role } from "../events/types.js";

/** Pi SDK 1.5.0 实测内置工具（dist/core/tools: read / grep / find / ls / bash / write / edit）。 */
export const SDK_BUILTIN_TOOLS: readonly string[] =
  ["read", "grep", "find", "ls", "bash", "write", "edit"];

/** 由 @solvex/pi-runtime 的 buildCustomTools() 注册并注入 session 的工具。 */
export const CUSTOM_TOOL_NAMES: readonly string[] = ["python_execute"];

/** 会话中真实可用的工具全集；ROLE_TOOLS 必须始终是它的子集（ADR-0008）。 */
export const AVAILABLE_TOOLS: ReadonlySet<string> =
  new Set<string>([...SDK_BUILTIN_TOOLS, ...CUSTOM_TOOL_NAMES]);

/**
 * 按角色收紧的工具白名单；review 保持只读，从根上消除 A2/F3（评审覆写 master_plan）。
 *
 * ADR-0008：移除旧 Python 运行时的 arxiv_search / web_search / webReader（占位符、
 * 从未注册），避免模型用 bash+curl 模拟联网检索陷入死循环。
 *
 * ADR-0009：writing 角色放宽为可发现、可检索整个共享工作区。此前只有
 * read/write/edit，模型既无法枚举目录（read 对目录返回 EISDIR），也无从得知
 * 02_programming/ 下真实 CSV 的文件名，只能读回 prompt 里出现过的占位符摘要，
 * 从而把「计算已完成」误写成「计算未完成」。
 */
export const ROLE_TOOLS: Record<Role, string[]> = {
  modeling: ["read", "grep", "find", "ls", "bash", "python_execute", "write", "edit"],
  programming: ["read", "write", "edit", "bash", "python_execute"],
  review: ["read", "grep", "find", "ls"],
  writing: ["read", "write", "edit", "ls", "find", "grep", "bash", "python_execute"],
  visualization: ["read", "write", "edit", "bash", "python_execute"],
};

export const REVIEW_TOOLS = ROLE_TOOLS.review;

/** 契约校验：返回每个角色里运行时并不存在的工具名（空数组表示契约成立）。 */
export function validateRoleTools(): { role: string; unknown: string[] }[] {
  return Object.entries(ROLE_TOOLS)
    .map(([role, tools]) => ({ role, unknown: tools.filter((t) => !AVAILABLE_TOOLS.has(t)) }))
    .filter((r) => r.unknown.length > 0);
}
