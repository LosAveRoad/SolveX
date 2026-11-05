import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { validateModelCatalog } from "@solvex/core";

/** 直接指向 pnpm 链接的真实 SDK 入口；不联网、不消耗任何额度。 */
const SDK_ENTRY = fileURLToPath(new URL(
  "../../packages/pi-runtime/node_modules/@earendil-works/pi-coding-agent/dist/index.js",
  import.meta.url));

const model = {
  id: "contract-model", name: "Contract Model",
  reasoning: false, input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 8192, maxTokens: 4096,
};

function writeCatalog(models: unknown, apiKey = "$SOLVEX_TEST_KEY"): string {
  const p = join(mkdtempSync(join(tmpdir(), "solvex-catalog-")), "models.json");
  writeFileSync(p, JSON.stringify({ providers: {
    "test-provider": { baseUrl: "https://example.invalid/v1", api: "openai-completions", apiKey, models },
  } }, null, 2));
  return p;
}

describe("Pi SDK 1.5.0 models.json 契约（离线、无真实凭据）", () => {
  it("合规 catalog：SDK 加载无错误、模型可解析、$VAR 凭据被识别", async () => {
    process.env.SOLVEX_TEST_KEY = "sk-not-a-real-key";
    const p = writeCatalog([model]);
    expect(validateModelCatalog(JSON.parse(readFileSync(p, "utf-8"))).ok).toBe(true);
    const { ModelRuntime } = await import(SDK_ENTRY);
    const rt = await ModelRuntime.create({ modelsPath: p, allowModelNetwork: false });
    expect(rt.getError()).toBeUndefined();
    expect(rt.getModel("test-provider", "contract-model")?.id).toBe("contract-model");
    expect(rt.hasConfiguredAuth("test-provider")).toBe(true);
    expect(rt.getProviderAuthStatus("test-provider")).toMatchObject({ configured: true, source: "environment" });
  }, 60_000);

  it("字符串数组 models 会被 SDK 整份拒绝，本地校验器提前拦截", async () => {
    const p = writeCatalog(["contract-model"]);
    expect(validateModelCatalog(JSON.parse(readFileSync(p, "utf-8"))).ok).toBe(false);
    const { ModelRuntime } = await import(SDK_ENTRY);
    const rt = await ModelRuntime.create({ modelsPath: p, allowModelNetwork: false });
    expect(rt.getError()).toMatch(/Invalid models\.json schema/);
    expect(rt.getProvider("test-provider")).toBeUndefined();
  }, 60_000);

  it("$ENV:VAR 不是 SDK 语法，会被当字面量导致凭据未配置", async () => {
    process.env.SOLVEX_TEST_KEY = "sk-not-a-real-key";
    const p = writeCatalog([model], "$ENV:SOLVEX_TEST_KEY");
    const { ModelRuntime } = await import(SDK_ENTRY);
    const rt = await ModelRuntime.create({ modelsPath: p, allowModelNetwork: false });
    expect(rt.hasConfiguredAuth("test-provider")).toBe(false);
  }, 60_000);
});
