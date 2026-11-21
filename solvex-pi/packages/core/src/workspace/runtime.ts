import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { THINKING_LEVELS, type ThinkingLevel } from "../events/types.js";
import type { ModelConfig, PhaseKey, PhaseModelConfig } from "../config/schema.js";
import { RUNTIME_FILE } from "./paths.js";
import type { WorkspaceInfo } from "./index.js";

/** 允许在启动运行时覆盖的字段；刻意不含 credentials / endpoints / apiKey。 */
export type RuntimeOverrides = {
  defaults?: Partial<ModelConfig["defaults"]>;
  byPhase?: Partial<Record<PhaseKey, Partial<PhaseModelConfig>>>;
  scopedModels?: string[];
  concurrency?: number;
  strict?: boolean;
  persistThinking?: boolean;
};

/** 生效配置的脱敏快照：每次运行写进自己的 runtime.json，后续改全局设置不会影响历史 run。 */
export type RuntimeConfig = Pick<ModelConfig,
  "defaults" | "byPhase" | "scopedModels" | "concurrency" | "strict" | "persistThinking">;

export type RuntimeSnapshot = {
  id: string;
  workspaceId?: string;
  createdAt: string;
  config: RuntimeConfig;
  overrides: RuntimeOverrides;
  inputs: { problemFilename?: string; files: string[] };
};

const PHASES: readonly PhaseKey[] = ["P1", "P2_IMPL", "P2_REVIEW", "P3", "P4"];
const shortText = (v: unknown, max = 200): string | undefined =>
  typeof v === "string" && v.length <= max ? v : undefined;
const thinking = (v: unknown): ThinkingLevel | undefined =>
  typeof v === "string" && (THINKING_LEVELS as readonly string[]).includes(v)
    ? v as ThinkingLevel : undefined;

/** 只接受白名单字段；未知字段、超长字符串、非法档位一律丢弃，杜绝把凭据写进快照。 */
export function sanitizeOverrides(raw: unknown): RuntimeOverrides {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const b = raw as Record<string, unknown>;
  const out: RuntimeOverrides = {};
  if (b.defaults && typeof b.defaults === "object" && !Array.isArray(b.defaults)) {
    const d = b.defaults as Record<string, unknown>;
    const defaults: RuntimeOverrides["defaults"] = {};
    if (d.provider !== undefined) { const v = shortText(d.provider); if (v !== undefined) defaults.provider = v; }
    if (d.model !== undefined) { const v = shortText(d.model); if (v !== undefined) defaults.model = v; }
    if (d.thinkingLevel !== undefined) { const v = thinking(d.thinkingLevel); if (v) defaults.thinkingLevel = v; }
    if (Object.keys(defaults).length) out.defaults = defaults;
  }
  if (b.byPhase && typeof b.byPhase === "object" && !Array.isArray(b.byPhase)) {
    const src = b.byPhase as Record<string, unknown>;
    const byPhase: NonNullable<RuntimeOverrides["byPhase"]> = {};
    for (const key of PHASES) {
      const v = src[key];
      if (!v || typeof v !== "object" || Array.isArray(v)) continue;
      const o = v as Record<string, unknown>;
      const phase: Partial<PhaseModelConfig> = {};
      if (o.provider !== undefined) { const p = shortText(o.provider); if (p !== undefined) phase.provider = p; }
      if (o.model !== undefined) { const m = shortText(o.model); if (m !== undefined) phase.model = m; }
      if (o.thinkingLevel !== undefined) { const t = thinking(o.thinkingLevel); if (t) phase.thinkingLevel = t; }
      if (Object.keys(phase).length) byPhase[key] = phase;
    }
    if (Object.keys(byPhase).length) out.byPhase = byPhase;
  }
  if (Array.isArray(b.scopedModels))
    out.scopedModels = b.scopedModels.filter((x): x is string => typeof x === "string" && x.length <= 200).slice(0, 32);
  if (typeof b.concurrency === "number" && Number.isFinite(b.concurrency))
    out.concurrency = Math.min(16, Math.max(1, Math.round(b.concurrency)));
  if (typeof b.strict === "boolean") out.strict = b.strict;
  if (typeof b.persistThinking === "boolean") out.persistThinking = b.persistThinking;
  return out;
}

/** 全局配置 + 本次覆盖 → 该 run 独占的生效配置。 */
export function buildRuntimeConfig(base: ModelConfig, overrides: RuntimeOverrides = {}): RuntimeConfig {
  return {
    defaults: { ...base.defaults, ...(overrides.defaults ?? {}) },
    byPhase: {
      ...base.byPhase,
      ...Object.fromEntries(Object.entries(overrides.byPhase ?? {}).map(([k, v]) => [k, {
        ...(base.byPhase[k as PhaseKey] ?? {}), ...v,
      }])),
    },
    scopedModels: overrides.scopedModels ?? [...base.scopedModels],
    concurrency: overrides.concurrency ?? Math.min(16, Math.max(1, base.concurrency)),
    strict: overrides.strict ?? base.strict,
    persistThinking: overrides.persistThinking ?? base.persistThinking,
  };
}

/** SolveXFlow 仍消费完整 ModelConfig；非运行参数沿用全局值但不写进快照。 */
export function toModelConfig(base: ModelConfig, runtime: RuntimeConfig): ModelConfig {
  return { ...base, ...runtime };
}

export function writeRuntime(ws: WorkspaceInfo, snapshot: RuntimeSnapshot): void {
  const f = join(ws.dir, RUNTIME_FILE);
  writeFileSync(f + ".tmp", JSON.stringify(snapshot, null, 2));
  renameSync(f + ".tmp", f);
}

export function readRuntime(ws: WorkspaceInfo): RuntimeSnapshot | undefined {
  const f = join(ws.dir, RUNTIME_FILE);
  if (!existsSync(f)) return undefined;
  try { return JSON.parse(readFileSync(f, "utf-8")) as RuntimeSnapshot; } catch { return undefined; }
}

/** 前端列表用的简短标签，不含任何凭据。 */
export function runtimeSummary(snapshot?: RuntimeSnapshot): { model: string; thinking: string;
  concurrency: number; strict: boolean } | undefined {
  if (!snapshot) return undefined;
  const c = snapshot.config;
  const d = c.defaults;
  const model = [d.provider, d.model].filter(Boolean).join("/") || "服务端默认";
  return { model, thinking: d.thinkingLevel, concurrency: c.concurrency, strict: c.strict };
}
