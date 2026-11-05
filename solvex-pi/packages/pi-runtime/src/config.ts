import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import {
  DEFAULT_CONFIG, THINKING_LEVELS, type ModelConfig, type ModelDescriptor,
  type ThinkingLevel, type PhaseKey, type RunRequest,
} from "@solvex/core";

export const DEFAULT_CONFIG_PATH = join(homedir(), ".solvex", "config.json");

export class ConfigStore {
  constructor(public readonly path: string = DEFAULT_CONFIG_PATH) {}
  load(): ModelConfig {
    let saved: Partial<ModelConfig> = {};
    if (existsSync(this.path)) {
      try { saved = JSON.parse(readFileSync(this.path, "utf-8")); } catch { /* 用默认 */ }
    }
    return { ...DEFAULT_CONFIG, ...saved,
      defaults: { ...DEFAULT_CONFIG.defaults, ...saved.defaults },
      byPhase: { ...DEFAULT_CONFIG.byPhase, ...saved.byPhase } };
  }
  save(patch: Partial<ModelConfig>): ModelConfig {
    const next = { ...this.load(), ...patch,
      defaults: { ...this.load().defaults, ...patch.defaults },
      byPhase: { ...this.load().byPhase, ...patch.byPhase } };
    mkdirSync(dirname(this.path), { recursive: true });
    writeFileSync(this.path, JSON.stringify(next, null, 2));
    return next;
  }
}

/** thinking 档位按模型能力裁剪（不支持 reasoning → off）。 */
export function thinkingLevelsForModel(model?: ModelDescriptor): ThinkingLevel[] {
  return model?.reasoning ? [...THINKING_LEVELS] : ["off"];
}

/** byPhase → RunRequest 覆盖；未配置回落 defaults（D5）。 */
export function phaseOverrides(config: ModelConfig, key: PhaseKey): Pick<RunRequest, "model" | "thinkingLevel" | "scopedModels"> {
  const c = config.byPhase[key];
  return {
    ...(c?.provider && c?.model ? { model: { provider: c.provider, id: c.model } }
      : config.defaults.provider && config.defaults.model
        ? { model: { provider: config.defaults.provider, id: config.defaults.model } } : {}),
    thinkingLevel: c?.thinkingLevel ?? config.defaults.thinkingLevel,
    ...(config.scopedModels.length ? { scopedModels: config.scopedModels } : {}),
  };
}
