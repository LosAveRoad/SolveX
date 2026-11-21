import type { Role } from "../events/types.js";
import { ROLE_TOOLS } from "./toolNames.js";

/**
 * 提示词不再列举工具名。system prompt 里只留 TOOL_LIST_PLACEHOLDER，
 * 由运行时从「实际注册进 session 的工具」生成清单后注入（ADR-0011）。
 */
export const TOOL_LIST_PLACEHOLDER = "{{AVAILABLE_TOOLS}}";

export type ToolDescriptor = {
  name: string;
  description: string;
  /** sdk = Pi 内置注册表，custom = buildCustomTools()，mcp = MCP server 的 tools/list。 */
  source?: "sdk" | "custom" | "mcp";
  /** MCP 工具可被限定给某些角色；未设置表示全部角色可用。 */
  roles?: Role[];
  server?: string;
  toolName?: string;
};

/** 纯函数：把发现到的工具渲染成权威清单。描述来自 SDK 定义 / 工具实现，不来自提示词。 */
export function renderToolList(tools: readonly ToolDescriptor[]): string {
  if (!tools.length) return "AVAILABLE TOOLS: no tools are registered for this session.";
  return [
    "AVAILABLE TOOLS (discovered from the tools registered in this session):",
    ...tools.map((t) => `- ${t.name}: ${t.source === "mcp" && t.server ? `[MCP ${t.server}] ` : ""}${t.description}`),
    "Only these tools are registered. Do NOT call or emulate a tool that is not listed above.",
  ].join("\n");
}

/** 替换所有占位符；没有占位符的提示词原样返回（其它角色可逐步接入）。 */
export function injectToolList(systemPrompt: string, tools: readonly ToolDescriptor[]): string {
  if (!systemPrompt.includes(TOOL_LIST_PLACEHOLDER)) return systemPrompt;
  return systemPrompt.split(TOOL_LIST_PLACEHOLDER).join(renderToolList(tools));
}

/** 按名字从发现结果里取描述；未发现的名字给兜底文案，绝不回落到提示词文本。 */
export function toolDescriptorsFor(names: readonly string[],
                                   catalog: readonly ToolDescriptor[]): ToolDescriptor[] {
  const byName = new Map(catalog.map((t) => [t.name, t]));
  return names.map((name) => byName.get(name) ?? { name, description: "Registered tool." });
}

/** 无运行时发现结果时的兜底（如 FakeRunner）：仍然从代码里的角色白名单生成。 */
export function fallbackToolCatalog(role: Role): ToolDescriptor[] {
  return toolDescriptorsFor(ROLE_TOOLS[role], []);
}
