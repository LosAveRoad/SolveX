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
 * 按角色收紧的工具白名单；review 为只读，从根上消除 A2/F3（评审覆写 master_plan）。
 *
 * R-2 修正：arxiv_search / web_search / webReader 属于旧 Python 运行时，在 Pi SDK
 * 中没有实现（曾以返回假结果的 placeholder 存在，且从未注册进 session）。把它们
 * 留在白名单里会让模型按提示词去「检索」，再用 bash + curl 模拟联网请求，超时后
 * 反复重试，永远走不到 WRITE 步骤。因此从 modeling 白名单移除。
 */
export const ROLE_TOOLS: Record<Role, string[]> = {
  modeling: ["read", "grep", "find", "ls", "bash", "python_execute", "write", "edit"],
  programming: ["read", "write", "edit", "bash", "python_execute"],
  review: ["read", "grep", "find", "ls"],
  writing: ["read", "write", "edit"],
  visualization: ["read", "write", "edit", "bash", "python_execute"],
};

export const REVIEW_TOOLS = ROLE_TOOLS.review;

/** 契约校验：返回每个角色里运行时并不存在的工具名（空数组表示契约成立）。 */
export function validateRoleTools(): { role: string; unknown: string[] }[] {
  return Object.entries(ROLE_TOOLS)
    .map(([role, tools]) => ({ role, unknown: tools.filter((t) => !AVAILABLE_TOOLS.has(t)) }))
    .filter((r) => r.unknown.length > 0);
}
