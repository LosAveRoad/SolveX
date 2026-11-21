import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "@solvex/web";
import { testPaths } from "./helpers.js";

let app: any;
let root: string;
let modelsPath: string;

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "solvex-endpoint-params-"));
  modelsPath = join(root, "models.json");
  const paths = testPaths();
  app = await createServer({ sessionRoot: paths.sessionRoot, workspaceRoot: paths.workspaceRoot,
    configPath: paths.configPath, modelsPath, mcpConfigPath: paths.mcpConfigPath, pingMs: 200 });
  await app.ready();
});

afterAll(async () => {
  await app.close();
  rmSync(root, { recursive: true, force: true });
});

describe("模型端点与参数由用户填写", () => {
  it("PUT 写入全部参数，catalog 能力也来自用户配置，响应不含明文", async () => {
    const r = await app.inject({ method: "PUT", url: "/api/models/endpoints", payload: {
      id: "my-llm", baseUrl: "https://api.example.com", api: "openai-completions",
      apiKey: "$MY_KEY", models: ["my-model"],
      contextWindow: 256000, maxTokens: 64000, reasoning: true, vision: true,
      cost: { input: 1.5, output: 6, cacheRead: 0.3, cacheWrite: 0 },
    } });
    expect(r.statusCode).toBe(200);

    const catalog = JSON.parse(readFileSync(modelsPath, "utf-8"));
    const model = catalog.providers["my-llm"].models[0];
    expect(model).toMatchObject({ id: "my-model", reasoning: true,
      input: ["text", "image"], contextWindow: 256000, maxTokens: 64000,
      cost: { input: 1.5, output: 6, cacheRead: 0.3, cacheWrite: 0 } });

    const d = (await app.inject({ method: "GET", url: "/api/models" })).json();
    expect(d.endpoints.find((e: any) => e.id === "my-llm")).toMatchObject({
      keyEnvVar: "MY_KEY", contextWindow: 256000, maxTokens: 64000,
      reasoning: true, vision: true, cost: { input: 1.5, output: 6 } });
    expect(JSON.stringify(d)).not.toContain("apiKey");
    expect(JSON.stringify(d)).not.toContain("$MY_KEY");

    // thinking 档位按用户填写的 reasoning 能力裁剪，不再恒为 off
    const levels = (await app.inject({ method: "GET",
      url: "/api/models/thinking-levels?model=my-model" })).json();
    expect(levels.levels.length).toBe(7);
  });

  it("不传参数时回退到安全默认值，保持旧调用兼容", async () => {
    const r = await app.inject({ method: "PUT", url: "/api/models/endpoints", payload: {
      id: "legacy", baseUrl: "https://legacy.example.com", api: "openai-completions",
      apiKey: "$LEGACY_KEY", models: ["legacy-model"],
    } });
    expect(r.statusCode).toBe(200);
    const catalog = JSON.parse(readFileSync(modelsPath, "utf-8"));
    const model = catalog.providers["legacy"].models[0];
    expect(model).toMatchObject({ id: "legacy-model", reasoning: false,
      input: ["text"], contextWindow: 128000, maxTokens: 8192 });
    expect(model.cost).toHaveProperty("cacheRead");
  });
});
