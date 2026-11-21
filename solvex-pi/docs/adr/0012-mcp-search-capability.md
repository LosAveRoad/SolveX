# ADR-0012：接入 MCP 提供搜索能力

- 状态：Accepted
- 日期：2026-11-06
- 关联：ADR-0008（幽灵工具）、ADR-0011（提示词工具清单代码发现）、ADR-0007（凭据脱敏）
- 依赖：`@earendil-works/pi-mcp@1.5.0`（与 Pi SDK 同版本精确锁）

## 背景

`modeling.system.md` 原本声明了 `arxiv_search` / `web_search` / `webReader` 三个工具，
但旧 Python 运行时之后、Pi SDK 1.5.0 里它们从未被注册。模型于是用 `bash + curl`
模拟联网检索，超时后无限重试，P1 永远走不到 WRITE（ADR-0008）。

ADR-0008 用离线覆盖策略压住症状，ADR-0011 把工具清单改成「运行时代码发现」。
本 ADR 补上真正的能力：**通过 MCP 连接外部服务，让 P1 可以用搜索**，并且不允许
再次出现「提示词写了、session 没有」的幽灵工具。

## 决策

1. **用官方 MCP 客户端，不重造协议层**。`@earendil-works/pi-mcp` 提供
   `McpClient`、`StdioTransport`、`StreamableHttpTransport` 和内存传输（测试用）。
   Pi SDK 自带的 `createMcpExtension` 默认 `exposure: codemode`，工具不会直接声明给模型，
   且工具名在连接后才产生，无法与 ADR-0011 的提示词注入同步；因此改为
   **自己连接 + 包装成 `customTools`**。
2. **一次真实连接 = 一次 `tools/list`**。`McpManager.ready()` 对每个启用的 server：
   建立传输 → `initialize` → `tools/list`，只有 server 真正返回的工具才被
   - 生成 `ToolDescriptor`（`source: "mcp"`、角色白名单、server 名、描述来自 server），
   - 包装成 Pi `customTools`（`parameters` 直接用 MCP `inputSchema`，`execute` 转发 `tools/call`）。
   连接失败/超时的 server 记为 `failed` 并产出 **0 个工具**，绝不列进提示词。
3. **与 ADR-0011 同源注入**。`PiAgentRunner.run()` 把发现的 MCP 工具名同时放进
   `options.tools`（SDK 的 allowlist 也管 customTools）、`options.customTools`，
   以及 `{{AVAILABLE_TOOLS}}` 注入的清单。三者是同一批名字，物理上不可能漂移。
   角色由配置 `roles` 控制（默认 `["modeling"]`），`tools` 可进一步限定只暴露哪几个工具。
4. **配置即代码，凭据只写引用**。`~/.solvex/mcp.json` 采用通用 `mcpServers` 形状：
   - `command` + `args` + `env`（stdio）或 `url` + `headers`（HTTP），二选一；
   - `env` / `headers` 里敏感键的值必须是 `$VAR` / `${VAR}` 引用，明文 `sk-...` 一律拒绝；
   - 支持 `roles`、`tools`、`description`、`enabled`、`timeoutMs`。
   `validateMcpConfig()` 是纯函数校验；`saveMcpConfig()` 校验通过才原子写入。
5. **连接按 `configPath + cwd` 复用**，进程内最多 8 个管理器，超出关闭最旧的。
   配置保存/刷新只重建对应 key，不影响正在跑的其它工作区 session。
6. **入口**：CLI `--mcp-config FILE`；Web `GET/PUT /api/mcp`、`POST /api/mcp/refresh`、
   `GET /api/mcp/path`；WebUI「模型设置 → MCP 搜索服务」显示每个 server 的连接状态、
   发现到的工具数，并可编辑 `mcp.json`。响应体不含明文密钥。

## 配置示例

```json
{
  "mcpServers": {
    "search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": { "BRAVE_API_KEY": "$BRAVE_API_KEY" },
      "description": "Web and academic search for modeling methods",
      "roles": ["modeling"],
      "tools": ["brave_web_search"],
      "timeoutMs": 30000
    }
  }
}
```

也可以接 HTTP MCP：`{"url": "https://mcp.example.com/mcp",
"headers": {"Authorization": "Bearer ${MCP_TOKEN}"}}`。

## 后果

- P1 的工具清单里会出现形如 `mcp__search__brave_web_search` 的条目，带 `[MCP search]`
  前缀和 server 自己给出的描述。`modeling.system.md` 的 METHODS 步与
  `OFFLINE_PLAN_POLICY` 已改成「以 AVAILABLE TOOLS 清单为准」：清单里有搜索工具就允许
  有限次检索，没有就不模拟联网、直接落盘。两种配置下提示词都不再自相矛盾。
- `ROLE_TOOLS` / `validateRoleTools()` 仍是内置工具的静态契约；MCP 工具是运行时增量，
  不属于角色白名单，也不写进 `AVAILABLE_TOOLS`。
- 没有 `mcp.json` 时行为与 2.1.1 完全一致：不连接、不注入、P1 离线。
- 新增依赖 `@earendil-works/pi-mcp@1.5.0`（已在 pnpm store 内，与 SDK 同版本）。
- 测试 `test/pi/mcp.test.ts` 用 `createInMemoryTransportPair()` 起一个真正说 MCP 协议的
  内存 server，覆盖 initialize / tools/list / tools/call，不依赖网络或外部进程。

## API key 由谁提供

MCP 协议本身没有凭据概念，SolveX 只是客户端，**自己不需要任何 API key**，
配置里的 `env` / `headers` 也完全可选。真正联网检索的是 MCP server，是否需要 key
由它决定：

| 形态 | 例子 | 需要 key？ |
| --- | --- | --- |
| 商业搜索 API 的 MCP server | Brave Search、Tavily、Exa | 需要，如 `BRAVE_API_KEY` / `TAVILY_API_KEY` |
| 自建 / 本地检索服务 | 自建 SearXNG、抓公开页面的 fetch server | 不需要（但可能有限流/合规约束） |
| 公开学术接口 | arXiv 公开 API 封装 | 通常不需要 |
| 远程 HTTP MCP + OAuth | 需交互登录的服务 | 本实现暂不支持 OAuth，见后续项 |

示例配置里的 `"BRAVE_API_KEY": "$BRAVE_API_KEY"` 就是 key 的引用：在**启动 SolveX
服务的 shell**里 `export BRAVE_API_KEY=...`，`resolveEnvRef()` 会展开后传给 server 子进程。
WebUI 只接受 `$VAR` 引用，没有「填写明文 key」的输入框，这是刻意的（ADR-0007 脱敏口径）。

如果引用的环境变量没设置，`resolveEnvRef()` 会得到空串，很多 server 在 `initialize`
阶段仍能连上，直到 `tools/call` 才返回 401 —— 排查成本很高。因此
`missingEnvRefs()` 会在连接时算出缺失的变量名，通过 `GET /api/mcp` 的
`servers[].missingEnv` 和 WebUI 的黄色提示提前暴露；`customTools.execute` 也会把
server 返回的错误以 `isError: true` 文本回给模型，不会静默成功。

## 内置搜索预设（2.1.3）

`packages/pi-runtime/src/mcpPresets.ts` 提供开箱预设，WebUI 一键启用
（`GET /api/mcp/presets` / `POST /api/mcp/presets/:id`），CLI 用 `--mcp-preset NAME`
（合并写入 `mcp.json`，幂等；同名 server 已存在时不覆盖）。

| 预设 | 传输 | 需要 key |
| --- | --- | --- |
| `deepseek` | 随包内置 stdio MCP server（`mcp-servers/deepseek-search.mjs`） | `DEEPSEEK_API_KEY` |
| `brave` | `npx @brave/brave-search-mcp-server --transport stdio`（官方现行版） | `BRAVE_API_KEY` |
| `brave-classic` | `npx @modelcontextprotocol/server-brave-search`（归档参考实现，工具名稳定） | `BRAVE_API_KEY` |
| `tavily` | `npx tavily-mcp@latest` | `TAVILY_API_KEY` |
| `exa` | `npx exa-mcp-server` | `EXA_API_KEY` |
| `duckduckgo` | `uvx duckduckgo-mcp-server`（需本机装 uv） | 无 |
| `fetch` | `uvx mcp-server-fetch`（读 URL 正文，配合搜索用） | 无 |

**预设不写 `tools` 白名单**：Brave / Tavily / Exa 的工具名互不相同
（`brave_web_search` / `tavily-search` / `web_search_exa`），且上游改版会变；
写死会把 `tools/list` 的发现结果过滤成 0 个，等于重新制造幽灵工具。
预设只描述传输方式，工具名与描述一律来自 server 自己。

### DeepSeek 官方搜索

DeepSeek 于 2026-10-17 开放自研搜索引擎的 Search / Fetch REST API：
`POST https://api.deepseek.com/v1/tools/search`（`query` / `count` / `need_content`）
与 `POST /v1/tools/fetch`（`url`），Bearer `$DEEPSEEK_API_KEY`。Search / Fetch 各
¥5/1000 次成功请求（仅 HTTP 200 且 Search `results` 非空、Fetch 返回正文才计费，
失败 / 无结果 / 超时不计费）；账号级限速 Search 100 QPS / Fetch 25 QPS，两者独立
（2026-11-09 按官方文档核对）。它是 REST 而不是 MCP，所以 SolveX 随包提供一个极简 stdio
MCP server（换行分隔 JSON-RPC，实现 `initialize` / `tools/list` / `tools/call`），
把两个端点包装成 `deepseek_search` 与 `deepseek_fetch`；stdout 只输出协议帧，
日志走 stderr。预设用 `process.execPath` + 脚本绝对路径启动，不依赖 PATH / cwd。
同一个 `DEEPSEEK_API_KEY` 也可用于「自定义 OpenAI 兼容端点」
（`https://api.deepseek.com/v1`，模型 `deepseek-flash`），即模型与检索共用一个 key。

## 已知后续项

- 未实现 OAuth 交互式登录；HTTP server 需要令牌时用 `$VAR` 引用环境变量。
- MCP 工具尚未纳入 `writablePrefixes` 写安全拦截（MCP 工具一般不写工作区文件）。
- 搜索工具目前只默认暴露给 `modeling` 角色；如需 P2/P4 检索，在配置的 `roles` 里追加即可。
