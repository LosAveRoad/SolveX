import { maskKey, THINKING_LEVELS, type ModelDescriptor, type ThinkingLevel } from "@solvex/core";
import { loadRealSdk } from "./sdk.js";

export type ModelRuntimeLike = {
  getAvailable(providerId?: string): Promise<any[]>;
  getModel(providerId: string, modelId: string): any;
  setRuntimeApiKey(providerId: string, apiKey: string): Promise<void>;
  refresh(options?: { allowNetwork?: boolean }): Promise<any>;
  listCredentials(): Promise<any[]>;
  getRegisteredProviderIds(): readonly string[];
};

let shared: ModelRuntimeManager | undefined;

/** 单例 ModelRuntime（T3.6 / §10.3.3）：多阶段复用，避免每阶段重建 catalog。 */
export class ModelRuntimeManager {
  private constructor(public readonly rt: ModelRuntimeLike, public readonly authPath?: string) {}

  static async create(opts: { authPath?: string; modelsPath?: string;
                              sdkRuntime?: ModelRuntimeLike } = {}): Promise<ModelRuntimeManager> {
    if (opts.sdkRuntime) return new ModelRuntimeManager(opts.sdkRuntime, opts.authPath);
    const sdk = await loadRealSdk();
    const rt = await sdk.ModelRuntime.create({
      authPath: opts.authPath, modelsPath: opts.modelsPath, refreshOnCreate: false,
    });
    return new ModelRuntimeManager(rt as unknown as ModelRuntimeLike, opts.authPath);
  }

  static async shared(opts: { authPath?: string; modelsPath?: string;
                              sdkRuntime?: ModelRuntimeLike } = {}): Promise<ModelRuntimeManager> {
    if (!shared) shared = await ModelRuntimeManager.create(opts);
    return shared;
  }
  static resetForTest(): void { shared = undefined; }

  /** 脱敏映射：响应体绝不含 apiKey / 任何明文密钥（R13）。 */
  async listAvailable(): Promise<ModelDescriptor[]> {
    const models = await this.rt.getAvailable();
    return (models ?? []).map((m: any) => ({
      provider: String(m.provider ?? m.providerId ?? ""),
      id: String(m.id ?? ""),
      name: m.name ? String(m.name) : undefined,
      reasoning: Boolean(m.reasoning ?? m.supportsReasoning ?? false),
      input: Array.isArray(m.input) ? m.input : ["text"],
      contextLimit: m.contextWindow ?? m.contextLimit,
      maxOutput: m.maxTokens ?? m.maxOutput,
      price: m.cost ? { input: m.cost.input ?? 0, output: m.cost.output ?? 0 } : undefined,
      available: true,
      source: (m.source === "models.json" ? "models.json" : "builtin") as ModelDescriptor["source"],
    }));
  }

  resolve(provider: string, id: string): any { return this.rt.getModel(provider, id); }
  scopedModels(ids: string[]): { model: any }[] {
    return ids.map((s) => {
      const [provider, ...rest] = s.split("/");
      const model = this.rt.getModel(provider, rest.join("/"));
      return model ? { model } : undefined;
    }).filter((x): x is { model: any } => x !== undefined);
  }
  /** 运行时注入凭据：只进内存，不写文件、不进日志。 */
  async setRuntimeApiKey(provider: string, key: string): Promise<void> {
    await this.rt.setRuntimeApiKey(provider, key);
  }
  async refresh(): Promise<void> { await this.rt.refresh({ allowNetwork: false }); }
  /** 凭据只回 masked。 */
  async credentials(): Promise<{ provider: string; source: "env" | "auth.json" | "runtime" | "models.json";
                                 masked: string; status: "ok" | "missing" }[]> {
    try {
      const list = await this.rt.listCredentials();
      return (list ?? []).map((c: any) => ({
        provider: String(c.providerId ?? c.provider ?? ""),
        source: (c.source ?? "runtime") as any,
        masked: maskKey(c.apiKey ?? c.masked ?? "configured"),
        status: (c.status ?? "ok") as "ok" | "missing",
      }));
    } catch { return []; }
  }
  thinkingLevelsFor(model: ModelDescriptor | undefined): ThinkingLevel[] {
    return model?.reasoning ? [...THINKING_LEVELS] : ["off"];
  }
}
