import { fileURLToPath } from "node:url";
import type { Role } from "@solvex/core";
import type { McpConfig, McpServerConfig } from "./mcp.js";

/**
 * DeepSeek 官方只提供 Search / Fetch REST API，没有 MCP server；SolveX 随包内置一个
 * stdio MCP server 把它包成标准工具。用绝对路径启动，任何工作目录都能拉起来。
 */
export const DEEPSEEK_MCP_SERVER_PATH =
  fileURLToPath(new URL("../mcp-servers/deepseek-search.mjs", import.meta.url));

/**
 * 常用搜索 / 网页读取 MCP server 的开箱预设。
 *
 * 两条硬规则：
 *  1. 预设**不写 `tools` 白名单**：各家工具名不同（brave_web_search / tavily-search /
 *     web_search_exa / ...），且会随版本变化；写死会让 tools/list 发现结果被过滤成 0 个，
 *     重新制造 ADR-0008 的「配置里写了但 session 没有」。工具一律由运行时发现。
 *  2. 凭据只写 `$VAR` 引用，由 `validateMcpConfig()` 统一校验，预设里绝无明文 key。
 *
 * 包名/启动参数来自各家官方文档与仓库（2026-11-07 核对）；上游迁移时改这里即可，
 * 不影响提示词资产。`docsUrl` 便于用户自行核对最新版。
 */
export type McpPreset = {
  id: string;
  name: string;
  summary: string;
  /** 是否需要申请商业搜索 API 的 key；false 表示零配置即可用。 */
  requiresKey: boolean;
  /** 启用前需要在启动 SolveX 的 shell 里 export 的变量名。 */
  envVars: string[];
  /** 该预设写入 mcpServers 时使用的 server 名。 */
  serverName: string;
  docsUrl: string;
  note?: string;
  config: McpServerConfigPreset;
};

type McpServerConfigPreset = McpServerConfig & { roles: Role[]; description: string; timeoutMs: number };

const stdio = (command: string, args: string[], env: Record<string, string> | undefined,
               description: string): McpServerConfigPreset => ({
  command, args, ...(env ? { env } : {}),
  roles: ["modeling"], description, timeoutMs: 30_000,
});

export const MCP_SEARCH_PRESETS: readonly McpPreset[] = [
  {
    id: "deepseek", name: "DeepSeek Search（官方，内置）",
    summary: "DeepSeek 自研搜索引擎 + 网页正文抓取，一个预设同时提供 search 与 fetch 两个工具",
    requiresKey: true, envVars: ["DEEPSEEK_API_KEY"], serverName: "deepseek",
    docsUrl: "https://api-docs.deepseek.com/zh-cn/guides/search",
    note: "官方 REST API 由 SolveX 内置的 stdio MCP server 包装，无需额外安装包；" +
          "Search / Fetch 各 ¥5/1000 次成功请求（失败、无结果、超时不计费），" +
          "账号级限速 Search 100 QPS / Fetch 25 QPS（2026-11-09 按官方文档核对）。" +
          "与 DeepSeek 模型端点可共用同一个 key",
    config: {
      command: process.execPath, args: [DEEPSEEK_MCP_SERVER_PATH],
      env: { DEEPSEEK_API_KEY: "$DEEPSEEK_API_KEY" },
      roles: ["modeling"], description: "DeepSeek official Search + Fetch API", timeoutMs: 30_000,
    },
  },
  {
    id: "brave", name: "Brave Search（官方版）",
    summary: "独立索引的通用网页搜索，官方维护的 MCP server，工具覆盖面最广",
    requiresKey: true, envVars: ["BRAVE_API_KEY"], serverName: "brave",
    docsUrl: "https://github.com/brave/brave-search-mcp-server",
    note: "官方新版需 --transport stdio；免费额度约 2000 次/月，需申请 key",
    config: stdio("npx", ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"],
      { BRAVE_API_KEY: "$BRAVE_API_KEY" }, "Official Brave Search MCP server"),
  },
  {
    id: "brave-classic", name: "Brave Search（经典参考实现）",
    summary: "modelcontextprotocol/servers 里的归档实现，文档最多、工具名稳定为 brave_web_search",
    requiresKey: true, envVars: ["BRAVE_API_KEY"], serverName: "brave-classic",
    docsUrl: "https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
    note: "已被官方版取代，但兼容性最好；与官方版二选一即可，不要同时启用",
    config: stdio("npx", ["-y", "@modelcontextprotocol/server-brave-search"],
      { BRAVE_API_KEY: "$BRAVE_API_KEY" }, "Classic Brave Search MCP server"),
  },
  {
    id: "tavily", name: "Tavily",
    summary: "为 LLM 优化的一体化搜索 + 正文提取，返回结果自带清洗过的文本",
    requiresKey: true, envVars: ["TAVILY_API_KEY"], serverName: "tavily",
    docsUrl: "https://docs.tavily.com/documentation/mcp",
    note: "本地 stdio 版；官方远程 HTTP 版走 OAuth，本实现暂不支持交互登录",
    config: stdio("npx", ["-y", "tavily-mcp@latest"],
      { TAVILY_API_KEY: "$TAVILY_API_KEY" }, "Tavily search and extract MCP server"),
  },
  {
    id: "exa", name: "Exa",
    summary: "语义/神经检索，适合找概念相近的论文与技术资料",
    requiresKey: true, envVars: ["EXA_API_KEY"], serverName: "exa",
    docsUrl: "https://github.com/exa-labs/exa-mcp-server",
    config: stdio("npx", ["-y", "exa-mcp-server"],
      { EXA_API_KEY: "$EXA_API_KEY" }, "Exa neural search MCP server"),
  },
  {
    id: "duckduckgo", name: "DuckDuckGo（零 key）",
    summary: "无需账号、无需 API key 的网页搜索，最适合先验证整条链路能跑通",
    requiresKey: false, envVars: [], serverName: "duckduckgo",
    docsUrl: "https://pypi.org/project/duckduckgo-mcp-server/",
    note: "通过 uvx 运行，需本机安装 uv；有速率限制，不适合高强度检索",
    config: stdio("uvx", ["duckduckgo-mcp-server"], undefined,
      "DuckDuckGo search and content fetch MCP server"),
  },
  {
    id: "fetch", name: "Fetch 网页正文（零 key）",
    summary: "把指定 URL 转成 Markdown 正文；配合任一搜索 server 使用，负责「读全文」",
    requiresKey: false, envVars: [], serverName: "fetch",
    docsUrl: "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    note: "通过 uvx 运行，需本机安装 uv；只负责读取 URL，本身不提供搜索",
    config: stdio("uvx", ["mcp-server-fetch"], undefined,
      "URL to Markdown fetch MCP server"),
  },
];

export function findMcpPreset(id: string): McpPreset | undefined {
  return MCP_SEARCH_PRESETS.find((p) => p.id === id);
}

/**
 * 把预设合并进现有配置。纯函数、不 mutate 入参；同名 server 默认拒绝覆盖，
 * 避免一键启用时抹掉用户手写过的配置。
 */
export function applyMcpPreset(current: McpConfig, id: string,
                               opts: { replace?: boolean } = {}): McpConfig {
  const preset = findMcpPreset(id);
  if (!preset) throw new Error(`未知的 MCP 预设: ${id}`);
  if (!opts.replace && current.mcpServers?.[preset.serverName])
    throw new Error(`工作区已存在同名 MCP 服务 ${preset.serverName}，请先在 mcp.json 中删除或改名`);
  return {
    mcpServers: { ...(current.mcpServers ?? {}), [preset.serverName]: { ...preset.config } },
  };
}
