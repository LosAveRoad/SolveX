import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import { ModelConfigService } from "../../apps/web/src/modelConfig.js";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "@solvex/web";
import { testPaths } from "./helpers.js";

let app: any;
let root: string;
let envPath: string;
let prevOverride: string | undefined;
let prevKey: string | undefined;

const MODELS = { providers: { deepseek: {
  baseUrl: "https://api.deepseek.com", api: "openai-completions", apiKey: "$DEEPSEEK_API_KEY",
  models: [{ id: "deepseek-chat", name: "DeepSeek Chat", api: "openai-completions",
    reasoning: false, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 65536, maxTokens: 8192 }],
} } };

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "solvex-key-persist-"));
  envPath = join(root, ".env");
  writeFileSync(envPath, "# 模板\nDEEPSEEK_API_KEY=\n");
  const modelsPath = join(root, "models.json");
  writeFileSync(modelsPath, JSON.stringify(MODELS));
  prevOverride = process.env.SOLVEX_ENV_FILE;
  prevKey = process.env.DEEPSEEK_API_KEY;
  delete process.env.DEEPSEEK_API_KEY;
  process.env.SOLVEX_ENV_FILE = envPath;
  const paths = testPaths();
  app = await createServer({ sessionRoot: paths.sessionRoot, workspaceRoot: paths.workspaceRoot,
    configPath: paths.configPath, modelsPath, pingMs: 200 });
  await app.ready();
});

afterAll(async () => {
  await app.close();
  if (prevOverride === undefined) delete process.env.SOLVEX_ENV_FILE;
  else process.env.SOLVEX_ENV_FILE = prevOverride;
  if (prevKey === undefined) delete process.env.DEEPSEEK_API_KEY;
  else process.env.DEEPSEEK_API_KEY = prevKey;
  rmSync(root, { recursive: true, force: true });
});

describe("WebUI 填写 API Key", () => {
  it("默认只进内存，不写 .env（保持 T5.12 语义）", async () => {
    const r = await app.inject({ method: "POST", url: "/api/models/api-key",
      payload: { provider: "deepseek", apiKey: "sk-temp-only-0001" } });
    expect(r.statusCode).toBe(200);
    expect(r.json()).toMatchObject({ ok: true, masked: "sk-••••" });
    expect(r.json().persisted).toBeUndefined();
    expect(readFileSync(envPath, "utf-8")).not.toContain("sk-temp-only-0001");
  });

  it("persist=true 显式写入 .env，响应只回 masked 与变量名", async () => {
    const r = await app.inject({ method: "POST", url: "/api/models/api-key",
      payload: { provider: "deepseek", apiKey: "sk-persisted-0002", persist: true } });
    expect(r.statusCode).toBe(200);
    const d = r.json();
    expect(d).toMatchObject({ ok: true, persisted: true, envVar: "DEEPSEEK_API_KEY" });
    expect(JSON.stringify(d)).not.toContain("sk-persisted-0002");
    expect(JSON.stringify(d)).not.toContain("apiKey");
    const raw = readFileSync(envPath, "utf-8");
    expect(raw).toContain("DEEPSEEK_API_KEY=sk-persisted-0002");
    expect(raw).toContain("# 模板");
    expect((raw.match(/DEEPSEEK_API_KEY=/g) ?? []).length).toBe(1);
    expect(process.env.DEEPSEEK_API_KEY).toBe("sk-persisted-0002");
  });

  it("SDK 运行时注入被凭据锁挡住时，仍能把 key 保存到 .env", async () => {
    const spy = vi.spyOn(ModelConfigService.prototype, "setApiKey")
      .mockRejectedValueOnce(new Error("Credential store locked"));
    try {
      const r = await app.inject({ method: "POST", url: "/api/models/api-key",
        payload: { provider: "deepseek", apiKey: "sk-fallback-0003", persist: true } });
      expect(r.statusCode).toBe(200);
      expect(r.json()).toMatchObject({ persisted: true, runtimeInjected: false });
      expect(readFileSync(envPath, "utf-8")).toContain("DEEPSEEK_API_KEY=sk-fallback-0003");
    } finally { spy.mockRestore(); }
  });
});
