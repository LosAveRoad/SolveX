import { THINKING_LEVELS } from "../events/types.js";
import type { ModelConfig } from "./schema.js";

/** D2 默认并行度 3（=1 等价旧版串行）；D4 默认 strict=false；D5 默认模型不硬编码。 */
export const DEFAULT_CONFIG: ModelConfig = {
  defaults: { thinkingLevel: "medium" },
  byPhase: {
    P1:        { provider: "", model: "", thinkingLevel: "high" },
    P2_IMPL:   { provider: "", model: "", thinkingLevel: "medium" },
    P2_REVIEW: { provider: "", model: "", thinkingLevel: "high" },
    P3:        { provider: "", model: "", thinkingLevel: "off" },
    P4:        { provider: "", model: "", thinkingLevel: "medium" },
  },
  scopedModels: [],
  thinkingLevels: [...THINKING_LEVELS],
  credentials: [],
  endpoints: [],
  concurrency: 3,
  strict: false,
  persistThinking: false,
};

export const SOLVEX_CONFIG_PATH = ".solvex/config.json";
