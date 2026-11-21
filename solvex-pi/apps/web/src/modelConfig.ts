import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { ConfigStore, thinkingLevelsForModel, sharedModelRuntime, resolveModelsPath } from "@solvex/pi-runtime";
import {
  THINKING_LEVELS, maskKey, validateModelCatalog,
  type ModelConfig, type ModelDescriptor, type ThinkingLevel,
} from "@solvex/core";

/** 无凭据环境的静态 catalog，让模型配置中心始终可用；有凭据时由 ModelRuntime 覆盖。 */
const STATIC_MODELS: ModelDescriptor[] = [
  { provider: "anthropic", id: "claude-sonnet-4-5", name: "Claude Sonnet 4.5", reasoning: true,
    input: ["text", "image"], contextLimit: 200000, price: { input: 3, output: 15 },
    available: false, source: "builtin" },
  { provider: "anthropic", id: "claude-opus-4-5", name: "Claude Opus 4.5", reasoning: true,
    input: ["text", "image"], contextLimit: 200000, price: { input: 15, output: 75 },
    available: false, source: "builtin" },
  { provider: "openai", id: "gpt-5", name: "GPT-5", reasoning: true,
    input: ["text", "image"], contextLimit: 128000, price: { input: 1.25, output: 10 },
    available: false, source: "builtin" },
  { provider: "openai", id: "gpt-5-mini", name: "GPT-5 mini", reasoning: false,
    input: ["text"], contextLimit: 128000, price: { input: 0.25, output: 2 },
    available: false, source: "builtin" },
  { provider: "google", id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", reasoning: true,
    input: ["text", "image"], contextLimit: 1000000, price: { input: 1.25, output: 10 },
    available: false, source: "builtin" },
];

const ENV_KEYS: Record<string, string> = {
  anthropic: "ANTHROPIC_API_KEY", openai: "OPENAI_API_KEY", google: "GOOGLE_API_KEY",
};

/** 模型端点与参数全部由用户填写；这里只是回显结构，绝不含明文密钥。 */
export type EndpointView = {
  id: string; baseUrl: string; api: string; keyEnvVar: string; models: string[];
  contextWindow: number; maxTokens: number; reasoning: boolean; vision: boolean;
  cost: { input: number; output: number; cacheRead: number; cacheWrite: number };
};
export type EndpointInput = {
  id: string; baseUrl: string; api: string; apiKey?: string; models: string[];
  contextWindow?: number; maxTokens?: number; reasoning?: boolean; vision?: boolean;
  cost?: Partial<EndpointView["cost"]>;
};

const ENV_REF_NAME = /^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$/;
function envVarFromRef(ref: unknown): string {
  const m = ENV_REF_NAME.exec(String(ref ?? "").trim());
  return m ? m[1] : "";
}
function positive(v: unknown, fallback: number): number {
  const n = Number(v); return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}
function nonNeg(v: unknown): number {
  const n = Number(v); return Number.isFinite(n) && n >= 0 ? n : 0;
}
function normalizeCost(c: any): EndpointView["cost"] {
  return { input: nonNeg(c?.input), output: nonNeg(c?.output),
           cacheRead: nonNeg(c?.cacheRead), cacheWrite: nonNeg(c?.cacheWrite) };
}

export class ModelConfigService {
  private readonly runtimeKeys = new Map<string, string>(); // 只内存，绝不落盘、不进日志
  private readonly envVars = new Map<string, string>(); // provider -> 环境变量名（绝不存值）
  private catalog: ModelDescriptor[] = STATIC_MODELS.map((m) => ({ ...m }));
  private endpoints: EndpointView[] = [];

  constructor(private readonly opts: { configPath?: string; modelsPath?: string } = {}) {
    this.refreshSync();
  }

  private get store(): ConfigStore { return new ConfigStore(this.opts.configPath); }
  private get modelsPath(): string {
    return resolveModelsPath(this.opts.modelsPath);
  }

  private refreshSync(): void {
    this.envVars.clear();
    const p = this.modelsPath;
    if (!existsSync(p)) return;
    try {
      const raw = JSON.parse(readFileSync(p, "utf-8"));
      if (!validateModelCatalog(raw).ok) return;
      const views: EndpointView[] = [];
      const extra: ModelDescriptor[] = [];
      for (const [id, v] of Object.entries(raw.providers ?? {}) as [string, any][]) {
        // 自定义端点的 apiKey 只允许 $VAR / ${VAR}；记住变量名即可判断 .env 是否已提供凭据。
        const name = envVarFromRef(v?.apiKey);
        if (name) this.envVars.set(id, name);
        const list = (Array.isArray(v.models) ? v.models : []) as any[];
        const first = typeof list[0] === "object" ? list[0] : {};
        views.push({
          id, baseUrl: String(v.baseUrl), api: String(v.api), keyEnvVar: name,
          models: list.map((m) => typeof m === "string" ? m : String(m?.id ?? "")),
          contextWindow: positive(first.contextWindow, 128000),
          maxTokens: positive(first.maxTokens, 8192),
          reasoning: Boolean(first.reasoning),
          vision: Array.isArray(first.input) && first.input.includes("image"),
          cost: normalizeCost(first.cost),
        });
        // catalog 的能力与限额同样取自用户填写的参数，不再硬编码。
        for (const m of list) {
          const mid = typeof m === "string" ? m : String(m?.id ?? "");
          if (!mid) continue;
          const def = typeof m === "object" ? m : {};
          const c = normalizeCost(def.cost);
          const vision = Array.isArray(def.input) && def.input.includes("image");
          extra.push({ provider: id, id: mid, reasoning: Boolean(def.reasoning),
            input: vision ? ["text", "image"] : ["text"],
            contextLimit: positive(def.contextWindow, 128000),
            maxOutput: positive(def.maxTokens, 8192),
            price: { input: c.input, output: c.output },
            available: false, source: "models.json" });
        }
      }
      this.endpoints = views;
      this.catalog = [...STATIC_MODELS.map((m) => ({ ...m })), ...extra];
    } catch { /* 保留静态 catalog */ }
  }

  /** 内置 provider 用约定变量名，自定义端点用 models.json 里声明的 $VAR 名；只回变量名。 */
  envVarForProvider(provider: string): string | undefined {
    return ENV_KEYS[provider] ?? this.envVars.get(provider);
  }

  private availability(m: ModelDescriptor): ModelDescriptor {
    const env = this.envVarForProvider(m.provider);
    const ok = this.runtimeKeys.has(m.provider) || (env ? Boolean(process.env[env]) : false);
    return { ...m, available: ok };
  }

  /** 只回 masked，响应体不含任何明文密钥（R13 / ADR-13）。 */
  get(): { models: ModelDescriptor[]; config: ModelConfig; thinkingLevels: ThinkingLevel[];
           credentials: any[]; endpoints: any[] } {
    const config = this.store.load();
    return {
      models: this.catalog.map((m) => this.availability(m)),
      config,
      thinkingLevels: [...THINKING_LEVELS],
      credentials: [...new Set(this.catalog.map((m) => m.provider))].map((provider) => {
        const env = this.envVarForProvider(provider);
        const fromEnv = env ? process.env[env] : undefined;
        const fromRuntime = this.runtimeKeys.get(provider);
        return { provider,
          source: fromRuntime ? "runtime" : fromEnv ? "env" : "models.json",
          masked: fromRuntime ? maskKey(fromRuntime) : fromEnv ? maskKey(fromEnv) : "",
          status: fromRuntime || fromEnv ? "ok" : "missing" };
      }),
      endpoints: this.endpoints.map((e) => ({ ...e })), // 含全部用户参数，但绝不含明文 apiKey
    };
  }

  save(patch: Partial<ModelConfig>): ModelConfig {
    const illegal = patch.thinkingLevels?.filter((l) => !THINKING_LEVELS.includes(l)) ?? [];
    if (illegal.length) throw new Error(`非法 thinking 档位: ${illegal.join(",")}`);
    return this.store.save(patch);
  }
  refresh(): void { this.refreshSync(); }
  async refreshRuntime(): Promise<void> {
    const runtime = await sharedModelRuntime({ modelsPath: this.modelsPath });
    if (!runtime) throw new Error("模型运行时初始化失败，请检查服务端配置");
    await runtime.refresh();
  }
  /** 运行时注入凭据：只进内存。 */
  async setApiKey(provider: string, key: string): Promise<void> {
    const runtime = await sharedModelRuntime({ modelsPath: this.modelsPath });
    if (!runtime) throw new Error("模型运行时初始化失败，请检查服务端配置");
    await runtime.setRuntimeApiKey(provider, key);
    this.runtimeKeys.set(provider, key);
  }
  setEndpoints(endpoints: EndpointInput[]): void {
    const providers: Record<string, any> = {};
    for (const e of endpoints) {
      // Pi SDK 1.5.0 只认 "$VAR" / "${VAR}"；旧写法 "$ENV:VAR" 在此转换。
      // 明文 Key 绝不落盘，统一指向运行时注入的环境变量。
      const ref = e.apiKey
        ? e.apiKey.startsWith("$ENV:") ? "$" + e.apiKey.slice(5)
          : /^\$\{?[A-Za-z_]/.test(e.apiKey) ? e.apiKey : "$SOLVEX_API_KEY"
        : "$SOLVEX_API_KEY";
      const cost = normalizeCost(e.cost);
      providers[e.id] = {
        baseUrl: e.baseUrl, api: e.api, apiKey: ref,
        // SDK schema：models 必须是对象数组、cost 四字段齐全；其余参数全部来自用户填写。
        models: e.models.map((id) => ({
          id, name: id, api: e.api,
          reasoning: Boolean(e.reasoning),
          input: e.vision ? ["text", "image"] : ["text"],
          cost,
          contextWindow: positive(e.contextWindow, 128000),
          maxTokens: positive(e.maxTokens, 8192),
        })),
      };
    }
    const p = this.modelsPath;
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, JSON.stringify({ providers }, null, 2));
    this.refreshSync();
  }
  thinkingLevels(modelId?: string): ThinkingLevel[] {
    if (!modelId) return [...THINKING_LEVELS];
    const m = this.catalog.find((x) => x.id === modelId || `${x.provider}/${x.id}` === modelId);
    return thinkingLevelsForModel(m);
  }
}
