import { SDK_BUILTIN_TOOLS, type ToolDescriptor } from "@solvex/core";
import { buildCustomTools } from "../extensions/solvex-tools.js";
import { fileURLToPath } from "node:url";

/** 已安装 SDK 的内置工具注册表（1.5.0: dist/core/tools/index.js）。 */
const SDK_TOOLS_MODULE = "../node_modules/@earendil-works/pi-coding-agent/dist/core/tools/index.js";
const oneLine = (s: unknown, fallback: string): string => {
  const v = typeof s === "string" && s.trim() ? s.trim().split("\n")[0] : "";
  return v.slice(0, 240) || fallback;
};

let cached: ToolDescriptor[] | undefined;

/** 从 SDK 自身导出的 allToolNames / createToolDefinition 发现内置工具及描述。 */
async function discoverSdkBuiltins(): Promise<ToolDescriptor[]> {
  const url = new URL(SDK_TOOLS_MODULE, import.meta.url);
  const mod: any = await import(/* @vite-ignore */ url.href);
  const names: string[] = mod.allToolNames ? [...mod.allToolNames] : [...SDK_BUILTIN_TOOLS];
  const out: ToolDescriptor[] = [];
  for (const name of names) {
    try {
      const def = mod.createToolDefinition(name, process.cwd());
      out.push({ name: String(def?.name ?? name),
        description: oneLine(def?.promptSnippet ?? def?.description, "Pi SDK built-in tool.") });
    } catch {
      out.push({ name, description: "Pi SDK built-in tool." });
    }
  }
  return out;
}

/**
 * 代码发现：内置工具问 SDK 注册表，自定义工具问 buildCustomTools()。
 * 结果按进程缓存；SDK 内部路径变动时回落到 SDK_BUILTIN_TOOLS（仍是代码，不是提示词）。
 * 绝不把提示词文本或幽灵工具名当作来源。
 */
export async function discoverToolCatalog(): Promise<ToolDescriptor[]> {
  if (cached) return cached;
  let builtins: ToolDescriptor[];
  try { builtins = await discoverSdkBuiltins(); }
  catch {
    builtins = [...SDK_BUILTIN_TOOLS].map((name) => ({ name, description: "Pi SDK built-in tool." }));
  }
  const custom: ToolDescriptor[] = (buildCustomTools() as any[]).map((t) => ({
    name: String(t.name), description: oneLine(t.description ?? t.label, "Custom tool."),
  }));
  const seen = new Set<string>();
  const all: ToolDescriptor[] = [];
  for (const t of [...builtins, ...custom]) {
    if (!t.name || seen.has(t.name)) continue;
    seen.add(t.name); all.push(t);
  }
  cached = all;
  return all;
}

/** 测试用：清空缓存，便于验证回落路径。 */
export function resetToolCatalogForTest(): void { cached = undefined; }

/** 便于诊断：发现结果里的工具名（不含任何描述文本）。 */
export async function discoveredToolNames(): Promise<string[]> {
  return (await discoverToolCatalog()).map((t) => t.name);
}

export const SDK_TOOLS_MODULE_PATH = fileURLToPath(new URL(SDK_TOOLS_MODULE, import.meta.url));
