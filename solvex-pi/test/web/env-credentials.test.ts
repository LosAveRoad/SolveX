import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ModelConfigService } from "../../apps/web/src/modelConfig.js";

const KEY = "SOLVEX_TEST_KEY";

describe("自定义端点凭据：从 $VAR 推导，.env 生效且只回 masked", () => {
  let dir: string;
  let previous: string | undefined;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "solvex-env-models-"));
    previous = process.env[KEY];
  });

  afterEach(() => {
    if (previous === undefined) delete process.env[KEY];
    else process.env[KEY] = previous;
    rmSync(dir, { recursive: true, force: true });
  });

  function service(): ModelConfigService {
    const modelsPath = join(dir, "models.json");
    writeFileSync(modelsPath, JSON.stringify({ providers: {
      custom: {
        baseUrl: "https://api.example.com/v1", api: "openai-completions",
        apiKey: `$${KEY}`,
        models: [{ id: "model-a", name: "Model A", api: "openai-completions", reasoning: false,
          input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 128000, maxTokens: 8192 }],
      },
    } }));
    return new ModelConfigService({ modelsPath, configPath: join(dir, "config.json") });
  }

  it("环境变量缺失时 provider 不可用、凭据 missing", () => {
    delete process.env[KEY];
    const d = service().get();
    expect(d.models.find((m) => m.provider === "custom")?.available).toBe(false);
    expect(d.credentials.find((c) => c.provider === "custom")).toMatchObject({ status: "missing" });
  });

  it("环境变量有值时 provider 可用、凭据 ok，响应体不含明文与 apiKey 字段", () => {
    process.env[KEY] = "sk-super-secret-9999";
    const d = service().get();
    expect(d.models.find((m) => m.provider === "custom")?.available).toBe(true);
    const c = d.credentials.find((x) => x.provider === "custom");
    expect(c).toMatchObject({ status: "ok", source: "env" });
    expect(c?.masked).not.toContain("super-secret");
    expect(JSON.stringify(d)).not.toContain("sk-super-secret-9999");
    expect(JSON.stringify(d)).not.toContain("apiKey");
  });
});
