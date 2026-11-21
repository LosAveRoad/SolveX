import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  validateMcpConfig, resolveEnvRef, loadMcpConfig, saveMcpConfig, missingEnvRefs,
  McpManager, getSharedMcpManager, resetSharedMcpManagerForTest,
} from "@solvex/pi-runtime";
import { createInMemoryTransportPair } from "@earendil-works/pi-mcp/testing";
import {
  modelingSystem, ROLE_TOOLS, injectToolList, toolDescriptorsFor, EventBus,
  TOOL_LIST_PLACEHOLDER,
} from "@solvex/core";
import { PiAgentRunner } from "@solvex/pi-runtime";
import { makeFakeSdk } from "./fakeSdk.js";

const cwd = () => mkdtempSync(join(tmpdir(), "solvex-mcp-"));

/** 一个真正说 MCP 协议的内存 server：initialize / tools/list / tools/call。 */
function fakeSearchServer() {
  const { client, server } = createInMemoryTransportPair();
  server.onMessage((msg: any) => {
    if (msg.method === "initialize") {
      void server.send({ jsonrpc: "2.0", id: msg.id, result: {
        protocolVersion: msg.params?.protocolVersion ?? "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "fake-search", version: "1.0.0" },
      }});
    } else if (msg.method === "tools/list") {
      void server.send({ jsonrpc: "2.0", id: msg.id, result: { tools: [
        { name: "web_search", description: "Search the web for recent methods",
          inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } },
        { name: "internal_debug", description: "Should be filtered by the tools whitelist",
          inputSchema: { type: "object", properties: {} } },
      ] } });
    } else if (msg.method === "tools/call") {
      void server.send({ jsonrpc: "2.0", id: msg.id, result: {
        content: [{ type: "text", text: `results for ${msg.params?.arguments?.query ?? ""}` }],
        isError: false,
      } });
    }
  });
  return { client, server };
}

async function connectedManager() {
  const { client, server } = fakeSearchServer();
  await server.start();
  const manager = new McpManager({ mcpServers: {
    search: { url: "https://example.invalid/mcp", description: "Web search",
      roles: ["modeling"], tools: ["web_search"], timeoutMs: 5000 },
  } }, { cwd: cwd(), transportFactory: () => client });
  await manager.ready();
  return { manager, server };
}

describe("ADR-0012 MCP 连接能力", () => {
  beforeEach(async () => { await resetSharedMcpManagerForTest(); });
  afterEach(async () => { await resetSharedMcpManagerForTest(); });

  it("配置校验：拒绝明文密钥、非法形状、非法角色，接受 $VAR 引用", () => {
    const ok = validateMcpConfig({ mcpServers: {
      search: { url: "https://example.com/mcp",
        headers: { Authorization: "Bearer ${SEARCH_TOKEN}" },
        env: { BRAVE_API_KEY: "$BRAVE_API_KEY" },
        roles: ["modeling", "writing"], tools: ["web_search"] },
    } });
    expect(ok.ok).toBe(true);
    const bad = validateMcpConfig({ mcpServers: {
      x: { command: "npx", url: "https://x/mcp", roles: ["hacker"],
           headers: { Authorization: "Bearer sk-plaintext123456789" } },
    } });
    expect(bad.ok).toBe(false);
    expect(bad.errors.join(" ")).toContain("明文密钥");
    expect(bad.errors.join(" ")).toContain("roles");
    expect(bad.errors.join(" ")).toContain("只能提供其一");
    expect(validateMcpConfig({ mcpServers: { "bad/name": { url: "https://x/mcp" } } }).ok).toBe(false);
  });

  it("$VAR 引用解析成环境变量，引用本身不会作为密钥发出", () => {
    process.env.SOLVEX_TEST_MCP_KEY = "resolved-value";
    expect(resolveEnvRef("Bearer ${SOLVEX_TEST_MCP_KEY}")).toBe("Bearer resolved-value");
    expect(resolveEnvRef("$SOLVEX_TEST_MCP_KEY")).toBe("resolved-value");
    expect(resolveEnvRef("Bearer $SOLVEX_MISSING_XYZ")).toBe("Bearer ");
    delete process.env.SOLVEX_TEST_MCP_KEY;
  });

  it("是否需要 API key 由 server 决定；缺引用变量时提前报出，不等到 tools/call 才失败", async () => {
    delete process.env.SOLVEX_MCP_TEST_MISSING_KEY;
    const cfg = { url: "https://example.invalid/mcp", roles: ["modeling"] as const,
      env: { BRAVE_API_KEY: "$SOLVEX_MCP_TEST_MISSING_KEY" },
      headers: { Authorization: "Bearer ${SOLVEX_MCP_TEST_MISSING_KEY}" } };
    expect(missingEnvRefs(cfg as any)).toEqual(["SOLVEX_MCP_TEST_MISSING_KEY"]);
    process.env.SOLVEX_MCP_TEST_MISSING_KEY = "set-now";
    expect(missingEnvRefs(cfg as any)).toEqual([]);
    delete process.env.SOLVEX_MCP_TEST_MISSING_KEY;

    // 完全不写 env/headers 的 server 也不需要任何 key（例如本地 SearXNG / arXiv 公开接口）
    expect(missingEnvRefs({ command: "npx", args: ["-y", "local-mcp"] })).toEqual([]);

    const { client, server } = fakeSearchServer();
    await server.start();
    const manager = new McpManager({ mcpServers: { search: cfg as any } },
      { cwd: cwd(), transportFactory: () => client });
    await manager.ready();
    expect(manager.status()[0]).toMatchObject({ state: "connected" });
    expect(manager.status()[0].missingEnv).toEqual(["SOLVEX_MCP_TEST_MISSING_KEY"]);
    await manager.close(); await server.close();
  });

  it("配置文件缺失 = 未启用；保存/回读只写校验通过的内容", () => {
    const p = join(cwd(), "mcp.json");
    expect(loadMcpConfig(p).config).toEqual({ mcpServers: {} });
    expect(loadMcpConfig(p).errors).toEqual([]);
    expect(saveMcpConfig({ mcpServers: { x: { url: "ftp://nope" } } }, p).ok).toBe(false);
    expect(existsSync(p)).toBe(false);
    const saved = saveMcpConfig({ mcpServers: {
      search: { url: "https://example.com/mcp", headers: { Authorization: "Bearer ${TOKEN}" } },
    } }, p);
    expect(saved.ok).toBe(true);
    expect(readFileSync(p, "utf-8")).not.toContain("sk-");
    expect(loadMcpConfig(p).config.mcpServers.search.url).toBe("https://example.com/mcp");
  });

  it("真实 tools/list 发现工具；未声明的工具不会变成幽灵工具", async () => {
    const { manager, server } = await connectedManager();
    try {
      const d = manager.descriptors();
      expect(d.map((x) => x.name)).toEqual(["mcp__search__web_search"]);
      expect(d[0].source).toBe("mcp");
      expect(d[0].roles).toEqual(["modeling"]);
      expect(d[0].description).toContain("Search the web");
      expect(manager.status()[0]).toMatchObject({ name: "search", state: "connected" });
      expect(manager.status()[0].tools).toEqual(["mcp__search__web_search"]);
    } finally { await manager.close(); await server.close(); }
  });

  it("包装成 customTools：按角色暴露，execute 转发 tools/call 并回传文本", async () => {
    const { manager, server } = await connectedManager();
    try {
      const tools = manager.customTools("modeling");
      expect(tools).toHaveLength(1);
      expect(tools[0].name).toBe("mcp__search__web_search");
      expect((tools[0].parameters as any).properties.query.type).toBe("string");
      const out = await tools[0].execute("call-1", { query: "graph neural networks" });
      expect(out.isError).toBe(false);
      expect(out.content[0].text).toBe("results for graph neural networks");
      expect(manager.customTools("review")).toEqual([]);
    } finally { await manager.close(); await server.close(); }
  });

  it("PiAgentRunner 把 MCP 工具同时放进 tools / customTools / 提示词", async () => {
    const { manager, server } = await connectedManager();
    const f = makeFakeSdk();
    try {
      await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk, mcpManager: manager }).run({
        role: "modeling", systemPrompt: modelingSystem(), task: "TASK", cwd: cwd(),
        taskId: "P1", phase: 1, tools: ROLE_TOOLS.modeling,
      });
      const options = f.createOptions[0];
      const listed = [...(f.loaderOptions[0].systemPromptOverride() as string)
        .matchAll(/^- ([a-z0-9_]+):/gm)].map((m) => m[1]);
      expect(listed).toContain("mcp__search__web_search");
      expect(options.tools).toContain("mcp__search__web_search");
      expect(options.customTools.map((t: any) => t.name)).toContain("mcp__search__web_search");
      expect(options.tools).toEqual(listed);
      expect((f.loaderOptions[0].systemPromptOverride() as string)).not.toContain(TOOL_LIST_PLACEHOLDER);
      expect((f.loaderOptions[0].systemPromptOverride() as string)).toContain("[MCP search]");
    } finally { await manager.close(); await server.close(); }
  });

  it("未配置 MCP 时行为不变：不连接、不注入额外工具", async () => {
    const f = makeFakeSdk();
    const manager = new McpManager({ mcpServers: {} }, { cwd: cwd() });
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk, mcpManager: manager }).run({
      role: "modeling", systemPrompt: modelingSystem(), task: "TASK", cwd: cwd(),
      taskId: "P1", phase: 1,
    });
    const prompt: string = f.loaderOptions[0].systemPromptOverride();
    expect(prompt).not.toContain("mcp__");
    expect(f.createOptions[0].tools).toEqual(ROLE_TOOLS.modeling);
    expect(f.createOptions[0].customTools.map((t: any) => t.name)).toEqual(["python_execute"]);
    await manager.close();
  });

  it("共享管理器按 configPath+cwd 复用，reset 后全部关闭", async () => {
    const dir = cwd();
    const a = getSharedMcpManager({ cwd: dir, configPath: join(dir, "none.json") });
    expect(getSharedMcpManager({ cwd: dir, configPath: join(dir, "none.json") })).toBe(a);
    expect(getSharedMcpManager({ cwd: dir + "-other", configPath: join(dir, "none.json") })).not.toBe(a);
    await resetSharedMcpManagerForTest();
    expect(getSharedMcpManager({ cwd: dir, configPath: join(dir, "none.json") })).not.toBe(a);
  });

  it("注入清单包含 MCP 描述，且没有占位符残留", async () => {
    const { manager, server } = await connectedManager();
    try {
      const [d] = manager.descriptors();
      const prompt = injectToolList(modelingSystem(), toolDescriptorsFor([d.name], [d]));
      expect(prompt).toContain(`- ${d.name}: [MCP search] ${d.description}`);
      expect(prompt).not.toContain(TOOL_LIST_PLACEHOLDER);
    } finally { await manager.close(); await server.close(); }
  });
});
