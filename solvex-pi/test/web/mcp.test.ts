import { describe, it, expect, afterEach } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { createServer } from "@solvex/web";
import { testPaths } from "./helpers.js";

const apps: Awaited<ReturnType<typeof createServer>>[] = [];
afterEach(async () => { for (const app of apps.splice(0)) await app.close(); });

describe("WebUI MCP 配置端点（ADR-0012）", () => {
  it("未配置时返回空配置与空服务列表，不联网也报错", async () => {
    const paths = testPaths();
    const app = await createServer({ ...paths }); apps.push(app);
    const r = await app.inject("/api/mcp");
    expect(r.statusCode).toBe(200);
    const d = r.json();
    expect(d.config).toEqual({ mcpServers: {} });
    expect(d.servers).toEqual([]);
    expect(d.errors).toEqual([]);
    expect(d.path).toBe(paths.mcpConfigPath);
    expect(existsSync(paths.mcpConfigPath)).toBe(false);
    const p = await app.inject("/api/mcp/path");
    expect(p.json().path).toBe(paths.mcpConfigPath);
  });

  it("拒绝明文密钥；合法配置可保存，响应永不回显密钥", async () => {
    const paths = testPaths();
    delete process.env.SOLVEX_MCP_TEST_MISSING_KEY;
    const app = await createServer({ ...paths }); apps.push(app);
    const bad = await app.inject({ method: "PUT", url: "/api/mcp", payload: {
      mcpServers: { search: { url: "https://example.com/mcp",
        headers: { Authorization: "Bearer sk-plaintextsecret123456" } } } } });
    expect(bad.statusCode).toBe(400);
    expect(existsSync(paths.mcpConfigPath)).toBe(false);

    const good = await app.inject({ method: "PUT", url: "/api/mcp", payload: {
      mcpServers: { search: { url: "https://127.0.0.1:1/mcp", timeoutMs: 1000,
        headers: { Authorization: "Bearer ${SOLVEX_MCP_TEST_MISSING_KEY}" },
        roles: ["modeling"], tools: ["web_search"] } } } });
    expect(good.statusCode).toBe(200);
    expect(readFileSync(paths.mcpConfigPath, "utf-8")).toContain("${SOLVEX_MCP_TEST_MISSING_KEY}");
    expect(JSON.stringify(good.json())).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
    expect(good.json().servers).toHaveLength(1);
    expect(good.json().servers[0]).toMatchObject({ name: "search", state: "failed", tools: [] });
    // key 没设时状态里直接给出提示，不用等到 tools/call 才暴露
    expect(good.json().servers[0].missingEnv).toEqual(["SOLVEX_MCP_TEST_MISSING_KEY"]);
    const get = (await app.inject("/api/mcp")).json();
    expect(get.config.mcpServers.search.roles).toEqual(["modeling"]);
    const refresh = await app.inject({ method: "POST", url: "/api/mcp/refresh" });
    expect(refresh.statusCode).toBe(200);
    expect(refresh.json().servers).toHaveLength(1);
  });

  it("预设目录可列出，一键启用写入配置且幂等防护生效", async () => {
    const paths = testPaths();
    const app = await createServer({ ...paths }); apps.push(app);
    const listed = await app.inject("/api/mcp/presets");
    expect(listed.statusCode).toBe(200);
    const presets = listed.json().presets;
    expect(presets.map((p: any) => p.id)).toContain("deepseek");
    expect(presets.find((p: any) => p.id === "deepseek")).toMatchObject({
      requiresKey: true, enabled: false, envVars: ["DEEPSEEK_API_KEY"] });
    // 目录只给元数据，不回传完整 config（里面含 $VAR 引用与路径）
    expect(presets.every((p: any) => !("config" in p))).toBe(true);

    const applied = await app.inject({ method: "POST", url: "/api/mcp/presets/deepseek" });
    expect(applied.statusCode).toBe(200);
    expect(readFileSync(paths.mcpConfigPath, "utf-8")).toContain("$DEEPSEEK_API_KEY");
    expect(applied.json().servers.map((s: any) => s.name)).toContain("deepseek");
    const after = (await app.inject("/api/mcp/presets")).json().presets
      .find((p: any) => p.id === "deepseek");
    expect(after.enabled).toBe(true);

    expect((await app.inject({ method: "POST", url: "/api/mcp/presets/deepseek" })).statusCode).toBe(400);
    expect((await app.inject({ method: "POST", url: "/api/mcp/presets/nope" })).statusCode).toBe(400);
  });
});
