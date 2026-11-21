# SolveX 2.0 — 基于 Pi coding-agent SDK 的多模型数学建模流水线

> 产品形态：**带 WebUI 的 CLI 工具**。旧 Python 自研运行时（`ToolCallAgent` / `llm.py` / `ToolCollection` / `compact.py`）已全部移除，四阶段编排模式保留；提示词资产按章节逐字保留，但 `modeling.system.md` 不再声明工具名，工具清单由运行时代码发现（见 ADR-0011）。

## 架构

```
apps/cli ─┐
apps/web ─┼─→ @solvex/core（零 Pi 依赖，AgentRunner 端口倒置）
          │      ├─ prompts/        提示词资产；工具清单占位符 {{AVAILABLE_TOOLS}}
          │      ├─ flow/           四阶段状态机 + 并行 DAG + 屏障
          │      ├─ contracts/      masterPlan / verdict / handoff
          │      ├─ gates/          质量门
          │      └─ events/         SolveXEvent v1.1 契约 + EventBus
          └─→ @solvex/pi-runtime（唯一 import @earendil-works/* 处）
                 ├─ PiAgentRunner  一阶段一 createAgentSession() + 发现并注入工具清单
                 ├─ toolDiscovery  从 SDK 注册表 / buildCustomTools() 发现工具
                 ├─ mcp            MCP 连接（stdio/HTTP）、tools/list 发现、tools/call 转发
                 ├─ eventBridge    thinking/turn/tool/usage/lifecycle → SolveXEvent
                 ├─ modelRuntime  单例 ModelRuntime + 凭据脱敏
                 └─ extensions/    python_execute + 路径安全拦截
```

- **D1**：仅使用官方 `@earendil-works/pi-coding-agent`（精确锁 `1.5.0`，见 `docs/adr/0001-pi-version-pin.md`）。
- **D2**：无依赖即并行 —— `P1 → P2-IMPL(N 并行) → 屏障 → P2-REVIEW(N 并行) → 屏障 → P3 纯代码聚合 → P4`，`concurrency` 默认 3，`=1` 等价旧版串行。
- **D6**：不做 `pi-package/`，提示词只保留 `packages/core/src/prompts/*.md` 一份真源。

## 环境要求

| 项 | 要求 |
| --- | --- |
| Node | **>= 22.19**（本仓库用 22.20.0，见 `.nvmrc`） |
| pnpm | 10.x |
| 模型凭据 | 至少 1 个 provider 的 API Key / OAuth（环境变量或 WebUI「模型设置」中运行时注入）；**运行前必须配置** |

```bash
pnpm install
npm run check        # typecheck + 全量测试
npm run build:web    # build the Pi-based workspace UI
```

## CLI

```bash
# 完整四阶段
npx tsx apps/cli/src/index.ts run -p problem.md -d data/ --concurrency 3 --mcp-config mcp.json
# 或一键启用内置搜索预设（写入 mcp.json，幂等）
npx tsx apps/cli/src/index.ts run -p problem.md -d data/ --mcp-preset deepseek

# 续跑 / 只写论文 / 质量门
npx tsx apps/cli/src/index.ts run --resume <session_id>   # 已完成的 Agent 调用从会话日志回放，中断的接着跑
npx tsx apps/cli/src/index.ts run --skip-to-writing -r <session_id>
npx tsx apps/cli/src/index.ts validate <session_id>
npx tsx apps/cli/src/index.ts inspect <session_id>

# 启动 WebUI 2.0（只绑定 127.0.0.1）
npx tsx apps/cli/src/index.ts serve --port 8000

# 凭据在 WebUI「模型设置」中配置；CLI 与 WebUI 始终使用真实模型运行时
```

参数与旧版 `run_flow.py` 1:1 兼容，新增 `--concurrency N` / `--strict` / `--session-dir` / `--mcp-config` / `--mcp-preset`；未提供演示模式，未知选项会直接报错。`--mcp-config` 指向 MCP 服务配置（默认 `~/.solvex/mcp.json`），`--mcp-preset` 一键启用内置搜索预设；P1 会自动获得其中发现的搜索工具。
`--strict` 对应 D4：质量门发现 Critical 问题时阻断进入 P4（默认关闭，只告警）。

## Workspace WebUI

The browser UI uses the real `@earendil-works/pi-web-ui` components. **One problem
= one workspace**: inputs live in the workspace, and every modeling run is an
independent runtime under that workspace. No chat message is required. See the
[workspace WebUI guide](docs/webui-workspaces.md) and [ADR-0010](docs/adr/0010-workspace-run-isolation.md).

```
~/.solvex/workspaces/{workspaceId}/
├── workspace.json          题目元信息（名称 / 输入清单 / 选中的主问题）
├── inputs/                 上传的原始题目与数据附件
└── runs/{runId}/           每次运行一个独立目录
    ├── runtime.json        生效配置快照 + 输入清单（脱敏、不可变）
    ├── events.jsonl        该 run 的事件流（SSE 回放源）
    ├── 00_problem/ data/   启动瞬间的输入快照
    └── 01_modeling/ 02_programming/ 04_paper/
```

- 同一工作区**可以并行启动多次运行**，各自有独立目录、事件流、阶段快照、
  取消控制器和 ZIP；切换/停止一个 run 不影响其他 run。
- 每次启动可传运行参数覆盖（模型分档、thinking、并发、strict），合并后的
  生效配置写进 `runtime.json`，后续改全局设置不会改写历史 run 的配置。
- 旧 `~/.solvex/sessions/{id}/` 与 `/api/run` 保持兼容，统一索引可回放；系统不会自动
  迁移或清理，但用户可在 WebUI 显式删除工作区 / 单次运行（运行中任务需先停止）。

主要端点：`POST /api/workspaces/:id/runs`（旧 `/run` 为别名）、
`GET /api/workspaces/:id/runs`、`GET /api/workspaces/:id/runs/:runId`、
`GET /api/runs/:id/runtime`；原有 14 个端点继续可用。

删除：`DELETE /api/workspaces/:id` 删除整个工作区（含 `inputs/`、题目、附件与全部
`runs/`），`DELETE /api/workspaces/:id/runs/:runId` 删除单次运行（新布局与旧平铺
`sessions/` 关联的历史 run 都支持）。目录必须落在托管根内、ID 需合法；仍有运行中
任务时返回 `409`，请先停止。WebUI 的侧栏工作区与运行记录右侧各有「×」按钮，
二次确认后删除并自动刷新列表。

Build before starting: `npm run build:web`. The existing modeling pipeline and
API remain available.

### Existing runtime features

浏览器打开 `http://127.0.0.1:8000/`，详见 `docs/webui-2.0.md`：

- **模型配置中心**：模型 ID、端点地址、API 类型、上下文长度、最大输出、能力标记与价格全部由用户填写；已取消内置模型下拉与按阶段分档，所有阶段统一使用填写的模型。运行时注入 Key（可勾选持久化到 `.env`），凭据**只回 `masked`**。
- **思考过程视图**：`thinking_start/_delta/_end` 按 `contentIndex` 流式重建，`*_end.content` 权威覆盖，默认折叠可展开，`redacted` 降级，64KB 截断，与产物严格隔离。
- **运行阶段视图**：外层 `stage`/`barrier`（编排层权威）+ 内层 `turn`/`tool`/`thinking`/`output`（Pi 会话细节），并行节点独立刷新，屏障显示 `3/5`。AI 生成过程中主视图自动跟随滚动到底部；用户手动上滚会暂停跟随，滚回底部后自动恢复。
- **顶部实时用量条**：模型 / thinking 档 / token / ¥；SSE `Last-Event-ID` 续传 + `/api/events` + `/api/stages` 刷新回放。

14 个 API 端点见设计文档 §10.8；旧 4 个端点保持兼容（含 multipart 上传修复与真实产物树）。

## 配置

- **本地凭据（推荐）**：项目根 `.env`（模板 `.env.example`，已被 `.gitignore` 忽略）。端点与 MCP 配置里的 `apiKey` 只能写 `$VAR` / `${VAR}` 引用，真实值统一写进 `.env`；`solvex run`、`solvex serve` 以及直接调用 `createServer()` 时由 Node 22 原生 `process.loadEnvFile` 自动加载（零新增依赖）。已在 shell 里 `export` 的同名变量优先、`.env` 缺失不阻断启动，可用 `SOLVEX_ENV_FILE` 指定其它路径。凭据接口仍只回 `masked`。WebUI「模型设置 → 模型凭据」可直接填写：默认只进内存（重启即丢），
勾选「保存到 .env」才显式写入该文件（权限 600、不进版本库），下次启动自动生效。
- **模型端点与参数**：`packages/pi-runtime/models.json`（可用 `SOLVEX_MODELS_PATH` 覆盖）。默认模型为 `deepseek-flash`（DeepSeek-V4.1-Flash-1017，OpenAI 兼容 `https://api.deepseek.com`，1M 上下文，支持 thinking / 视觉）；旧名 `deepseek-chat` 已于 2026-07 下线，不要再使用。WebUI「模型设置 → 模型端点与参数」可填写模型 ID、Base URL、API 类型、密钥 `$VAR` 引用、Context Window、Max Tokens、thinking / 视觉能力与价格，保存即写入该文件并刷新运行时；不再有写死的参数或内置模型下拉。密钥必须写成 `$VAR` / `${VAR}`，`models` 必须是含 `id` 的对象数组（Pi SDK 1.5.0 schema）。
- **运行配置**：`config.json` 的 `defaults.model` 由用户填写（格式 `provider/model`，例如 `deepseek/deepseek-flash`）；`byPhase` 不再单独选择模型，保存运行设置时统一同步为同一个模型，避免残留旧模型名。
- 运行配置：`~/.solvex/config.json`（`defaults` / `byPhase` / `scopedModels` / `concurrency` / `strict` / `persistThinking`）。WebUI 可直接编辑并保存即刷新。
- MCP 配置：`~/.solvex/mcp.json`（`mcpServers`：`command/args/env` 或 `url/headers`，`roles` / `tools` / `enabled` / `timeoutMs`）。**SolveX 本身不需要 API key**；是否需要由所选 MCP server 决定（Brave/Tavily 等商业搜索要 key，本地 SearXNG、arXiv 公开接口等可不要）。敏感值只能写 `$VAR` / `${VAR}` 引用，并在启动服务前 `export` 好；`/api/mcp` 与 WebUI 会提示哪些环境变量没设。工具由运行时 `tools/list` 发现后自动进入提示词。详见 [ADR-0012](docs/adr/0012-mcp-search-capability.md)。
- 内置预设：`GET /api/mcp/presets` / `POST /api/mcp/presets/:id`，或在 WebUI「模型设置 → MCP 搜索服务」一键启用。含 DeepSeek（官方 Search + Fetch，由随包内置 MCP server 包装）、Brave（官方/经典）、Tavily、Exa、DuckDuckGo（零 key）、Fetch（零 key）。预设不写死工具名白名单，避免上游改名后出现幽灵工具。
- 会话产物：WebUI 工作区运行写入 `~/.solvex/workspaces/{id}/runs/{runId}/`；CLI 与旧版 `/api/run` 仍写 `~/.solvex/sessions/{id}/`。两者目录契约一致（`00_problem / data / 01_modeling / 02_programming / 04_paper`，见设计文档 §2.5）。

## 测试

```bash
npm run check                 # tsc + vitest
npx vitest run                # 380 passed / 1 skipped（真实模型集成需 PI_TEST_MODEL）
PI_TEST_MODEL=<provider/id> npx vitest run test/pi/integration.test.ts
```

`test/` 分层：`prompts`（章节级逐字快照 + 工具代码发现）、`flow`（并行 DAG / 四阶段 / resume / abort）、`gates`、`pi`（事件桥接 / 适配器 / 模型运行时）、`web`（14 端点 / SSE / store 三视图）、`cli`、`regression`（23 个旧问题）。

## 文档

| 文件 | 内容 |
| --- | --- |
| `SolveX-Pi-Migration.md` | 迁移设计规格 v1.1（现状盘点、目标架构、ADR、风险、验收基线） |
| `SolveX-Pi-Migration-Plan.md` | 9 阶段实施计划（TDD 任务粒度） |
| `docs/MIGRATION-STATUS.md` | **本次实施完成状态 + Go/No-Go 清单** |
| `docs/regression-report.md` | 23 个旧问题逐条结论 |
| `docs/webui-2.0.md` | WebUI 使用说明 |
| `docs/benchmark.md` | 真实模型基准（4 轮数据驱动迭代）+ 性能与成本基线 |
| `docs/webui-workspaces.md` | 工作区 WebUI 使用说明（多 runtime / API） |
| `docs/adr/*.md` | 关键决策记录（0010 = 工作区与运行隔离；0011 = 提示词工具清单代码发现；0012 = MCP 搜索能力；0013 = 会话日志续跑与各 Agent 上下文来源；0014 = 共享数据集、复现门禁、评审可跑代码；0015 = 评审、修复、论文以提交工具结束） |
