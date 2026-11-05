import { fileURLToPath } from "node:url";
import { ModelRuntimeManager } from "./modelRuntime.js";

/** 包内默认 models.json（可用 SOLVEX_MODELS_PATH 或显式参数覆盖）。 */
export const DEFAULT_MODELS_PATH = fileURLToPath(new URL("../models.json", import.meta.url));

export function resolveModelsPath(explicit?: string): string {
  return explicit ?? process.env.SOLVEX_MODELS_PATH ?? DEFAULT_MODELS_PATH;
}

/**
 * 真实运行时使用的 ModelRuntime 单例。
 *
 * createAgentSession 的 modelRuntime 选项（SDK 1.5.0）决定会话能看到哪些
 * provider / 模型；不注入时 SDK 会回退到 ~/.pi/agent 的默认配置，导致
 * config.json 的分档模型、scopedModels 与自定义端点全部失效。
 *
 * 初始化失败时返回 undefined 让调用方降级，不阻断 --fake 演示。
 */
export async function sharedModelRuntime(opts: { modelsPath?: string; authPath?: string } = {}) {
  try {
    return await ModelRuntimeManager.shared({
      modelsPath: resolveModelsPath(opts.modelsPath),
      ...(opts.authPath ? { authPath: opts.authPath } : {}),
    });
  } catch (e) {
    process.stderr.write(`[solvex] ModelRuntime 初始化失败，回退 SDK 默认配置: ${(e as Error)?.message ?? e}\n`);
    return undefined;
  }
}
