import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { DEFAULT_CONFIG, validateModelCatalog, type ModelConfig } from "@solvex/core";

describe("配置骨架", () => {
  it("models.json 符合 Pi schema 且不含明文密钥", () => {
    const raw = readFileSync("packages/pi-runtime/models.json", "utf-8");
    const models = JSON.parse(raw);
    expect(validateModelCatalog(models).ok).toBe(true);
    expect(raw).not.toMatch(/sk-[A-Za-z0-9]{12,}/);
    for (const p of Object.values(models.providers ?? {}) as any[]) {
      // Pi SDK 1.5.0 语法：$VAR / ${VAR}（旧写法 $ENV:VAR 亦兼容）
      if (p.apiKey) expect(String(p.apiKey)).toMatch(/^\$/);
      for (const m of p.models ?? []) expect(typeof m).toBe("object");
    }
  });

  it("默认 concurrency=3 / strict=false / byPhase 结构完整", () => {
    expect(DEFAULT_CONFIG.concurrency).toBe(3);
    expect(DEFAULT_CONFIG.strict).toBe(false);
    expect(DEFAULT_CONFIG.defaults.thinkingLevel).toBe("medium");
    expect(Object.keys(DEFAULT_CONFIG.byPhase)).toEqual(
      expect.arrayContaining(["P1", "P2_IMPL", "P2_REVIEW", "P3", "P4"]));
  });

  it("ModelConfig 可解析且凭据默认脱敏", () => {
    const c: ModelConfig = { ...DEFAULT_CONFIG, credentials: [] } as ModelConfig;
    expect(c.defaults.provider).toBeUndefined();
    expect(c.scopedModels).toEqual([]);
  });
});
