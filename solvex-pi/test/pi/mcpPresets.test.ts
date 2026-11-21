import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createServer, type Server } from "node:http";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import {
  MCP_SEARCH_PRESETS, findMcpPreset, applyMcpPreset, DEEPSEEK_MCP_SERVER_PATH,
} from "@solvex/pi-runtime";
import { validateMcpConfig, missingEnvRefs, McpManager } from "@solvex/pi-runtime";

describe("常用搜索 MCP 预设", () => {
  it("id / serverName 唯一，且每个预设本身就是一份合法配置", () => {
    expect(new Set(MCP_SEARCH_PRESETS.map((p) => p.id)).size).toBe(MCP_SEARCH_PRESETS.length);
    expect(new Set(MCP_SEARCH_PRESETS.map((p) => p.serverName)).size).toBe(MCP_SEARCH_PRESETS.length);
    for (const p of MCP_SEARCH_PRESETS) {
      const v = validateMcpConfig({ mcpServers: { [p.serverName]: p.config } });
      expect(v.ok, `${p.id}: ${v.errors.join("; ")}`).toBe(true);
    }
  });

  it("预设不写 tools 白名单、不含明文密钥（工具一律由 tools/list 发现）", () => {
    for (const p of MCP_SEARCH_PRESETS) {
      expect((p.config as any).tools, p.id).toBeUndefined();
      expect(JSON.stringify(p.config)).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
      for (const v of Object.values({ ...(p.config.env ?? {}), ...(p.config.headers ?? {}) }))
        expect(String(v)).toMatch(/\$\{?[A-Za-z_]/);
    }
  });

  it("envVars 与实际引用的环境变量一致", () => {
    for (const p of MCP_SEARCH_PRESETS) {
      if (!p.requiresKey) { expect(p.envVars).toEqual([]); continue; }
      for (const name of p.envVars) delete process.env[name];
      expect(missingEnvRefs(p.config).sort(), p.id).toEqual([...p.envVars].sort());
      for (const name of p.envVars) process.env[name] = "dummy";
      expect(missingEnvRefs(p.config), p.id).toEqual([]);
      for (const name of p.envVars) delete process.env[name];
    }
  });

  it("applyMcpPreset 纯函数合并且拒绝覆盖同名 server", () => {
    const current = { mcpServers: { custom: { url: "https://example.com/mcp" } } };
    const next = applyMcpPreset(current, "deepseek");
    expect(Object.keys(next.mcpServers).sort()).toEqual(["custom", "deepseek"]);
    expect(Object.keys(current.mcpServers)).toEqual(["custom"]);
    expect(() => applyMcpPreset(next, "deepseek")).toThrow(/已存在同名/);
    expect(() => applyMcpPreset(current, "nope")).toThrow(/未知的 MCP 预设/);
    expect(applyMcpPreset(next, "deepseek", { replace: true }).mcpServers.deepseek)
      .toEqual(findMcpPreset("deepseek")!.config);
  });

  it("DeepSeek 预设有官方来源、内置脚本与两个工具", () => {
    const p = findMcpPreset("deepseek")!;
    expect(p.requiresKey).toBe(true);
    expect(p.envVars).toEqual(["DEEPSEEK_API_KEY"]);
    expect(p.docsUrl).toContain("deepseek.com");
    expect(existsSync(DEEPSEEK_MCP_SERVER_PATH)).toBe(true);
    expect(p.config.args?.[0]).toBe(DEEPSEEK_MCP_SERVER_PATH);
    expect(p.config.command).toBe(process.execPath);
  });
});

/** 真起一个 stdio 子进程 + 假 DeepSeek HTTP 服务，验证内置 MCP server 的协议与转发。 */
describe("DeepSeek 内置 MCP server 端到端", () => {
  let http: Server;
  let base: string;

  beforeAll(async () => {
    http = createServer((req, res) => {
      let body = "";
      req.on("data", (c) => { body += String(c); });
      req.on("end", () => {
        const payload = JSON.parse(body || "{}");
        res.setHeader("content-type", "application/json");
        if (req.url?.endsWith("/search")) {
          res.writeHead(200);
          res.end(JSON.stringify({ results: [{ title: "Graph Neural Networks",
            url: "https://example.com/gnn", summary: "A survey of GNN methods",
            date: "2026-01-01", authority: 3 }] }));
        } else if (req.url?.endsWith("/fetch")) {
          res.writeHead(200);
          res.end(JSON.stringify({ title: "Fetched page", content: `# Body\n\nread ${payload.url}` }));
        } else { res.writeHead(404); res.end("{}"); }
      });
    });
    await new Promise<void>((r) => http.listen(0, "127.0.0.1", () => r()));
    const port = (http.address() as any).port;
    base = `http://127.0.0.1:${port}/v1/tools`;
    process.env.DEEPSEEK_API_BASE_URL = base;
    process.env.DEEPSEEK_API_KEY = "test-key";
  });

  afterAll(async () => {
    delete process.env.DEEPSEEK_API_BASE_URL;
    delete process.env.DEEPSEEK_API_KEY;
    await new Promise<void>((r) => http.close(() => r()));
  });

  it("真实 stdio 握手 → tools/list 发现 → tools/call 转发并回传文本", async () => {
    const preset = findMcpPreset("deepseek")!;
    const manager = new McpManager({ mcpServers: { deepseek: preset.config } },
      { cwd: tmpdir() });
    try {
      await manager.ready();
      expect(manager.status()[0]).toMatchObject({ name: "deepseek", state: "connected" });
      const names = manager.descriptors().map((d) => d.name);
      expect(names).toContain("mcp__deepseek__deepseek_search");
      expect(names).toContain("mcp__deepseek__deepseek_fetch");

      const tools = manager.customTools("modeling");
      const search = tools.find((t: any) => t.name === "mcp__deepseek__deepseek_search");
      const out = await search.execute("call-1", { query: "graph neural networks", count: 3 });
      expect(out.isError).toBe(false);
      expect(out.content[0].text).toContain("Graph Neural Networks");
      expect(out.content[0].text).toContain("https://example.com/gnn");

      const fetchTool = tools.find((t: any) => t.name === "mcp__deepseek__deepseek_fetch");
      const fetched = await fetchTool.execute("call-2", { url: "https://example.com/gnn" });
      expect(fetched.isError).toBe(false);
      expect(fetched.content[0].text).toContain("read https://example.com/gnn");
    } finally { await manager.close(); }
  });

  it("缺少 DEEPSEEK_API_KEY 时错误以 isError 文本回给模型，不静默成功", async () => {
    delete process.env.DEEPSEEK_API_KEY;
    const preset = findMcpPreset("deepseek")!;
    const manager = new McpManager({ mcpServers: { deepseek: preset.config } },
      { cwd: tmpdir() });
    try {
      await manager.ready();
      const search = manager.customTools("modeling")
        .find((t: any) => t.name === "mcp__deepseek__deepseek_search");
      const out = await search.execute("call-3", { query: "anything" });
      expect(out.isError).toBe(true);
      expect(out.content[0].text).toContain("DEEPSEEK_API_KEY is not set");
    } finally {
      process.env.DEEPSEEK_API_KEY = "test-key";
      await manager.close();
    }
  });
});
