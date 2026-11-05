import type { ThinkingLevel } from "../events/types.js";

export type ModelDescriptor = {
  provider: string; id: string; name?: string;
  reasoning: boolean;
  input: ("text" | "image")[];
  contextLimit?: number; maxOutput?: number;
  price?: { input: number; output: number };
  available: boolean;
  source: "builtin" | "models.json" | "extension";
};

export type PhaseKey = "P1" | "P2_IMPL" | "P2_REVIEW" | "P3" | "P4";
export type PhaseModelConfig = { provider: string; model: string; thinkingLevel?: ThinkingLevel };

export type ModelConfig = {
  defaults: { provider?: string; model?: string; thinkingLevel: ThinkingLevel };
  byPhase: Partial<Record<PhaseKey, PhaseModelConfig>>;
  scopedModels: string[];
  thinkingLevels: ThinkingLevel[];
  credentials: { provider: string; source: "env" | "auth.json" | "runtime" | "models.json";
                 masked: string; status: "ok" | "missing" }[];
  endpoints: { id: string; baseUrl: string; api: string; models: string[] }[];
  concurrency: number;
  strict: boolean;
  persistThinking: boolean;
};

export type CatalogValidation = { ok: boolean; errors: string[] };

/** Pi SDK 1.5.0 接受的凭据引用形式：$VAR / ${VAR}（官方文档语法），
 *  另兼容本项目旧写法 $ENV:VAR；明文密钥一律拒绝。 */
const ENV_REF = /^(?:\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$ENV:[A-Za-z_][A-Za-z0-9_]*)$/;

/** 校验 Pi models.json catalog 结构（providers.*.{baseUrl, api, apiKey?, models[]}）。
 *  · apiKey 只允许环境变量引用，杜绝明文密钥入库；
 *  · models 元素必须是含 id 的对象（SDK 真实 schema）——字符串数组会让 SDK
 *    整份 config 校验失败并静默丢弃所有自定义 provider。 */
export function validateModelCatalog(catalog: unknown): CatalogValidation {
  const errors: string[] = [];
  if (!catalog || typeof catalog !== "object") return { ok: false, errors: ["catalog 不是对象"] };
  const providers = (catalog as any).providers;
  if (!providers || typeof providers !== "object") return { ok: false, errors: ["缺少 providers"] };
  for (const [id, p] of Object.entries(providers) as [string, any][]) {
    if (!p || typeof p !== "object") { errors.push(`${id}: 非对象`); continue; }
    for (const k of ["baseUrl", "api", "models"]) {
      if (!(k in p)) errors.push(`${id}: 缺少 ${k}`);
    }
    if (!Array.isArray(p.models)) {
      errors.push(`${id}: models 必须是数组`);
    } else {
      p.models.forEach((m: any, i: number) => {
        if (!m || typeof m !== "object" || typeof m.id !== "string" || !m.id)
          errors.push(`${id}: models[${i}] 必须是含 id 的对象（Pi SDK schema）`);
      });
    }
    if (p.apiKey !== undefined && !ENV_REF.test(String(p.apiKey)))
      errors.push(`${id}: apiKey 必须是环境变量引用（$VAR / \${VAR}），禁止明文`);
  }
  return { ok: errors.length === 0, errors };
}

/** 只回 masked 凭据，绝不返回明文。 */
export function maskKey(key: string | undefined): string {
  if (!key) return "";
  if (key.startsWith("$")) return "$ENV:••••";
  if (key.length <= 8) return "••••";
  return `${key.slice(0, 3)}••••${key.slice(-4)}`;
}
