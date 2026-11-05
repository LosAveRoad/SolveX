import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { ConfigStore, thinkingLevelsForModel } from "@solvex/pi-runtime";
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

export class ModelConfigService {
  private readonly runtimeKeys = new Map<string, string>(); // 只内存，绝不落盘、不进日志
  private catalog: ModelDescriptor[] = STATIC_MODELS.map((m) => ({ ...m }));
  private endpoints: { id: string; baseUrl: string; api: string; models: string[] }[] = [];

  constructor(private readonly opts: { configPath?: string; modelsPath?: string } = {}) {
    this.refreshSync();
  }

  private get store(): ConfigStore { return new ConfigStore(this.opts.configPath); }
  private get modelsPath(): string {
    return this.opts.modelsPath ?? new URL("../packages/pi-runtime/models.json", import.meta.url).pathname;
  }

  private refreshSync(): void {
    const p = this.modelsPath;
    if (!existsSync(p)) return;
    try {
      const raw = JSON.parse(readFileSync(p, "utf-8"));
      if (!validateModelCatalog(raw).ok) return;
      this.endpoints = Object.entries(raw.providers ?? {}).map(([id, v]: [string, any]) => ({
        id, baseUrl: String(v.baseUrl), api: String(v.api),
        // SDK 合规的 models 是对象数组；对外仍暴露 id 字符串列表
        models: (v.models ?? []).map((m: any) => typeof m === "string" ? m : String(m?.id ?? "")),
      }));
      const extra: ModelDescriptor[] = [];
      for (const e of this.endpoints) for (const id of e.models)
        extra.push({ provider: e.id, id, reasoning: false, input: ["text"],
          available: false, source: "models.json" });
      this.catalog = [...STATIC_MODELS.map((m) => ({ ...m })), ...extra];
    } catch { /* 保留静态 catalog */ }
  }

  private availability(m: ModelDescriptor): ModelDescriptor {
    const env = ENV_KEYS[m.provider];
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
        const env = ENV_KEYS[provider];
        const fromEnv = env ? process.env[env] : undefined;
        const fromRuntime = this.runtimeKeys.get(provider);
        return { provider,
          source: fromRuntime ? "runtime" : fromEnv ? "env" : "models.json",
          masked: fromRuntime ? maskKey(fromRuntime) : fromEnv ? maskKey(fromEnv) : "",
          status: fromRuntime || fromEnv ? "ok" : "missing" };
      }),
      endpoints: this.endpoints.map((e) => ({ ...e })), // 不含 apiKey
    };
  }

  save(patch: Partial<ModelConfig>): ModelConfig {
    const illegal = patch.thinkingLevels?.filter((l) => !THINKING_LEVELS.includes(l)) ?? [];
    if (illegal.length) throw new Error(`非法 thinking 档位: ${illegal.join(",")}`);
    return this.store.save(patch);
  }
  refresh(): void { this.refreshSync(); }
  /** 运行时注入凭据：只进内存。 */
  setApiKey(provider: string, key: string): void { this.runtimeKeys.set(provider, key); }
  setEndpoints(endpoints: { id: string; baseUrl: string; api: string; apiKey?: string; models: string[] }[]): void {
    const providers: Record<string, any> = {};
    for (const e of endpoints) {
      // Pi SDK 1.5.0 只认 "$VAR" / "${VAR}"；旧写法 "$ENV:VAR" 在此转换。
      // 明文 Key 绝不落盘，统一指向运行时注入的环境变量。
      const ref = e.apiKey
        ? e.apiKey.startsWith("$ENV:") ? "$" + e.apiKey.slice(5)
          : /^\$\{?[A-Za-z_]/.test(e.apiKey) ? e.apiKey : "$SOLVEX_API_KEY"
        : "$SOLVEX_API_KEY";
      providers[e.id] = {
        baseUrl: e.baseUrl, api: e.api, apiKey: ref,
        // SDK schema：models 必须是对象数组，cost 需含四个字段，否则整份
        // models.json 校验失败，所有自定义 provider 会被静默丢弃。
        models: e.models.map((id) => ({
          id, name: id, api: e.api, reasoning: false, input: ["text"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 128000, maxTokens: 8192,
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
