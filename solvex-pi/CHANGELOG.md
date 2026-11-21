# Changelog

## 2.4.0 — 2026-11-20（提交工具：评审、修复、论文以一次被接受的提交结束）

详见 ADR-0015。
- **提交工具**：`RunRequest.submit` 把一个提交工具注册进这一次调用，只有它的检查接受了提交才算交付。检查不合格时，原因作为工具错误回给模型，模型在同一轮里补齐后再提交；调用结束时还没提交，就在同一会话里催（评审 2 次、修复 2 次、P4 5 次）。
- **`submit_review(verdict, review)`**：结论只能是 SATISFIED 或 NEEDS_REVISION，正文不少于 400 字，NEEDS_REVISION 必须带修复步骤。取代 REPORT_FOLLOWUP 和 VERDICT_FOLLOWUP；从回复文字解析评审的旧逻辑暂时保留为兜底。
- **`submit_fix(summary)`**：可以选择不改（评审也会误判），在说明里写理由即可；改了文件的评审修复必须同时更新 `results_summary.md`。每次修复改了哪些文件都按哈希指纹记录（基线落盘，续跑后沿用）：r6 里 Model 3 的 3 次修复一个文件都没改，当时无从发现。
- **`submit_paper(memo)`**：检查时跑论文完整性门禁；题面要求备忘录时，备忘录是必填参数，SolveX 把它写成 `memo.tex` 插进论文。论文门禁新增占位符检查（`PHOLDER`、`TODO` 等）。
- 提交结果写进 Pi 会话日志，回放和续跑时恢复。
- **续跑修复**：「修复后摘要是否更新」改为按修复请求时落盘的指纹判断，不再比较修改时间；评审文件内容不变就不重写。r7 续跑实测：旧逻辑在回放时把评审文件的修改时间刷新，进而在已完成的会话末尾发起了新的真实模型调用。
- 测试：全量 **380 passed / 1 skipped**。

## 2.3.0 — 2026-11-20（质量优先：共享数据集 + 复现门禁 + 评审可跑代码）

详见 ADR-0014。
- **规划节点先看数据、建共享数据集**：P1 拥有完整权限，检查数据后在 `01_modeling/shared_data/` 产出清洗后的分析表、数据字典与校验记录，再基于它写计划；没建就同会话追问一次。实现提示附数据集说明。共享数据集与 master_plan 在 P1 之后只读（按 P1 结束时的快照还原，修复了并行评审下的还原竞态）。
- **结果契约 + 复现门禁**：每个模型交付 `run.py` 与 `results.json`，摘要数字只能抄自 `results.json`；编排层在实现后与每轮修复后重跑 `run.py` 比对结果，失败就把 stderr / 差异发回实现会话，最多 2 次。
- **评审可以跑代码**：评审工具加 `bash`、`python_execute`，草稿写 `.solvex/scratch/`；对实现、共享数据集、master_plan 的改动在评审后自动还原。
- **预算放宽**：轮次上限 建模 60 / 编程 90 / 评审 50 / 写作 100；基准思考等级改为 xhigh。
- **交付物门禁**：P1、实现、P4 结束时交付物不全（r6 实测 GLM 5.3 Flash 会说完"接下来我要……"就停下），就在同一会话里列出缺失项让它接着做（P1 4 次、实现 3 次、P4 3 次），取代单次计划重试与摘要补写。
- **评审必须有书面正文**：评审最终回复去掉结论行后不足 400 字，就在同一评审会话里要求写出书面评审（不重做调查）。r6 实测：6 次评审里 2 次以空回复结束，Model 1 只读了 3 个文件、追问结论后直接判通过；Model 3 第 3 轮空回复导致修复拿到空意见。
- **P4 论文完整性门禁**：每个计划模型一节、结论、真实摘要（≥300 字，r6 停在占位符 `PHOLDER`）、`\end{document}`，题面要求时还有备忘录；缺的部分在同一写作会话里催它接着写（最多 5 次）。r6 实测：写完引言和 Model 1 就以空回复结束，旧门禁只看文件在不在。
- **长上下文降思考档**：会话上下文超过 150K 时 xhigh 降到 high。上下文探针重放 r6 真实会话：177K 下 max 5/9、high 9/9；126K 以内 30/30 正常；大海捞针 583K 仍 5/5。压缩默认沿用 Pi（不提前压缩，可选 `compactAtTokens`）；基准窗口改为 512K。
- 基准脚本遇到模型调用失败时用日志续跑自动重试（等待 1/2/4/8/10/10 分钟，最多 6 次）；新增 `--resume <会话 id>`，退出后可在同一工作区接着跑。
- 基准题面删除 P1 的"第一步必须 write、写完即停"约束。
- 测试：全量 **361 passed / 1 skipped**。

## 2.2.0 — 2026-11-20（会话日志续跑 + 上下文来源修正）

详见 ADR-0013。
- **断点续跑基于 Pi 会话日志**：每次 Agent 调用写一份 JSONL（`<run>/.solvex/journal/`，按语义 key 命名）。重跑同一个 run 时，已完成的调用回放（不调用模型），中断的从日志接着跑（轮次预算与用量延续），编排层不再按模型猜测跳过。修复旧策略的 3 个问题：部分续跑时被跳过的模型从汇总/论文里消失；评审中断后续跑评审被整体跳过；兜底摘要被当成已完成。删除 `--from-model`（N 从未生效）。
- **Web 续跑**：`POST /api/resume/:id` 与界面「从断点续跑」；沿用首次运行的题面、配置与数据说明，并等待上一次流水线完全停下。
- **一个 Agent 一个会话**：摘要补写、自检修订、评审修复意见都直接发进该模型的实现会话（不另开修复 Agent），继承计划片段、代码思路和已算出的结果；修复沿用实现节点的模型配置与写权限；P1 重试发进同一会话。
- **评审循环**：每个模型最多评审 3 次（评审 → 修复 → 复审），通过即止，第 3 次修复后直接放行；每轮只带本轮意见，上一轮的丢弃；每轮评审落盘 `*_review_r{n}.md`；修复后摘要未更新则补一轮摘要；评审漏写结论行时在同一评审会话追问，仍无结论但列了问题则按需要修订处理（r5 实测：漏写结论被当作通过）。P3/P4 不携带评审状态（取消 provisional 标注）。
- **评审**：独立的评审 system prompt，评审内容只发送一次（此前同一段文本既当 system prompt 又当任务）。
- **题面按阶段生效**：`<!-- solvex:phase P1 -->` 标记段只给列出的阶段，P2 起追加说明；基准题面 `problem-focused.md` 的 P1 专用约束已加标记。
- 测试：全量 **336 passed / 1 skipped**。

## 2.1.4 — 2026-11-20（真实模型基准 + 数据驱动修复）

以 GLM 5.3 Flash 跑 4 轮端到端基准（`bench/`，数据见 `docs/benchmark.md`），按实测证据修复：
- **写隔离真正生效**：`safetyExtension` 挂进每个真实 session（此前仅单测调用）；前缀与路径按 cwd 解析为绝对路径比较。实测并行改写共享 master_plan.md 拦截率 0/3 → 3/3。
- **失败如实上报**：SDK 重试预算 3 次 → 6 次指数退避（覆盖实测约 50 s 上游中断）；重试耗尽抛 `AgentRunError`；P4 产物门（无 main.tex 判失败）；maxTurns 截断与模型故障分开处理（`turnCapped`）。
- **轮次预算 Steering**：剩 3 轮时 `session.steer()` 提醒落盘交付物。Agent 自写 results_summary 0/3 → 3/3。
- **用量口径**：只在 message_end 计一次；计入 cacheRead/cacheWrite；失败调用计入；同任务累加。上报值与 gateway 实计的偏差从 2.6×/0.06× 收敛到逐 token 一致。
- **交叉评审闭环**：评审结论从只读评审者的输出解析，并由编排层落盘 `*_review.md`。NEEDS_REVISION 接住率 0/3 → 3/3，触发定向修复 3 次。
- 测试：新增 11 例回归，全量 **321 passed / 1 skipped**。

## 2.1.3 — 2026-11-07（常用搜索 MCP 预设 + DeepSeek 官方搜索）

### 新增
- **内置搜索预设库** `packages/pi-runtime/src/mcpPresets.ts`：DeepSeek（官方，内置）、
  Brave（官方版 / 经典参考实现）、Tavily、Exa、DuckDuckGo（零 key）、Fetch 网页正文（零 key）
  共 7 个。每个预设带 `envVars` / `requiresKey` / `docsUrl` / `note`。
  **刻意不写 `tools` 白名单**——各家工具名不同且会随版本变，写死会把 `tools/list`
  发现结果过滤成 0 个，重新制造幽灵工具。预设只是传输配置，工具仍由运行时发现。
- **DeepSeek 官方 Search / Fetch 集成**：官方只有 REST API
  （`POST /v1/tools/search`、`/v1/tools/fetch`，Bearer `$DEEPSEEK_API_KEY`，约 ¥5/1000 次、5 QPS），
  没有 MCP server。SolveX 随包内置 `packages/pi-runtime/mcp-servers/deepseek-search.mjs`
  （stdio JSON-RPC MCP server），把两个端点包装成 `deepseek_search` / `deepseek_fetch`
  工具，仍走现有 `tools/list` → `customTools` → 提示词注入链，无需额外安装包。
  支持 `site:` / `lang:` / `after:` 等查询语法，Search 返回带 authority/date 的摘要，
  Fetch 返回 Markdown 正文。
- **入口**：Web `GET /api/mcp/presets`（目录 + 是否已启用 + 缺失环境变量）、
  `POST /api/mcp/presets/:id`（一键启用，合并写入 `mcp.json`，同名 server 拒绝覆盖）；
  WebUI「模型设置 → MCP 搜索服务」新增预设卡片，显示是否需要 key、缺失变量与官方文档链接；
  CLI `--mcp-preset NAME`（写入 `--mcp-config` 指向的配置，幂等）。
- `applyMcpPreset()` 纯函数合并不 mutate；DeepSeek 预设用 `process.execPath` +
  脚本绝对路径启动，不依赖 PATH 与工作目录。

### 说明与工程
- 包名/启动参数按 2026-11-07 各家官方文档核对：Brave 经典实现
  `@modelcontextprotocol/server-brave-search` 已被官方 `@brave/brave-search-mcp-server` 取代，
  两者都提供但标注「二选一」；Tavily 远程 HTTP 版走 OAuth，本实现暂不支持。
- 预设不代管任何密钥，`$VAR` 引用与 `missingEnvRefs()` 检查沿用 2.1.2。
- `vitest.config.ts` `testTimeout` 60s：真实 SDK 首次 import 在双 worker 下偶发 30s+ 抖动。
- 测试：新增 `test/pi/mcpPresets.test.ts`（7 例，含**真起 stdio 子进程 + 假 DeepSeek HTTP
  服务**的端到端协议测试、缺 key 的 `isError` 路径）、Web 预设端点、CLI 参数与未知预设失败。
- 全量基线：**291 passed / 1 skipped**（50 个测试文件 + 1 skip 的真实模型集成）；
  typecheck 与 `build:web` 通过。

## 2.1.2 — 2026-11-06（MCP 连接能力提供搜索，ADR-0012）

### 新增
- **MCP 连接层**：`packages/pi-runtime/src/mcp.ts` 用官方 `@earendil-works/pi-mcp@1.5.0`
  （与 SDK 同版本精确锁）连接 stdio / HTTP MCP server，启动时 `initialize` + `tools/list`。
  只有 server 真正返回的工具才会被包装成 Pi `customTools`（`tools/call` 转发），
  连接失败/超时的 server 产出 0 个工具 —— 从根上杜绝 ADR-0008 的幽灵工具。
- **与 ADR-0011 同源**：`PiAgentRunner` 把发现的 MCP 工具名同时写进
  `options.tools`（SDK allowlist 也管 customTools）、`options.customTools` 和
  `{{AVAILABLE_TOOLS}}` 注入清单，三者是同一批名字。工具名形如
  `mcp__<server>__<tool>`，清单里带 `[MCP <server>]` 前缀和 server 自己的描述。
- **配置**：`~/.solvex/mcp.json`（`mcpServers`：`command/args/env` 或 `url/headers`，
  外加 `roles` / `tools` / `description` / `enabled` / `timeoutMs`）。
  `validateMcpConfig()` 拒绝明文密钥，敏感值必须是 `$VAR` / `${VAR}` 引用；
  `saveMcpConfig()` 校验通过才原子落盘。默认暴露给 `modeling` 角色。
  连接按 `configPath + cwd` 复用，最多 8 个管理器。
- **入口**：CLI `--mcp-config FILE`；Web `GET/PUT /api/mcp`、`POST /api/mcp/refresh`、
  `GET /api/mcp/path`；WebUI「模型设置 → MCP 搜索服务」显示连接状态/发现工具数，
  可直接编辑 `mcp.json` 并保存重连。响应体不含明文凭据。

### 变更
- `modeling.system.md` 的 METHODS 步与 `OFFLINE_PLAN_POLICY` 不再写死「本运行时没有网络」，
  改为**以 AVAILABLE TOOLS 清单为准**：清单里有搜索工具就允许有限次检索，没有就不模拟
  联网、直接落盘。两种配置下提示词都不自相矛盾，且策略文本仍不含任何具体工具名。
- `ToolDescriptor` 增加 `source` / `roles` / `server` / `toolName`；`renderToolList` 给 MCP
  工具加来源前缀。
- `packages/pi-runtime/package.json` 新增 `@earendil-works/pi-mcp` 直接依赖；
  `tsconfig.base.json` 与 `vitest.config.ts` 增加对应路径映射（`/testing` 别名须排在基础别名前）。
- `vitest.config.ts` `testTimeout` 放宽到 30s，消除真实 SDK 冷启动在双 worker 下的偶发假红。
- **API key 可观测性**：MCP 协议本身不需要 key，`env` / `headers` 可选，是否需要由
  MCP server 决定。缺 `export` 的 `$VAR` 原本会被 `resolveEnvRef()` 静默解析成空串，
  直到 `tools/call` 才报 401；新增 `missingEnvRefs()`，在 `GET /api/mcp` 的
  `servers[].missingEnv` 与 WebUI 黄色提示中提前列出缺失变量。README / ADR-0012 补
  「谁需要 API key」说明表（商业搜索要 key；自建 SearXNG、arXiv 公开接口可不要）。

### 测试
- 新增 `test/pi/mcp.test.ts`（9 例）：用 `createInMemoryTransportPair()` 起一个真正说 MCP
  协议的内存 server，覆盖 initialize / tools/list / tools/call、配置脱敏、角色隔离、
  `tools` 白名单过滤、未声明工具不成幽灵工具、PiAgentRunner 三处一致性、共享管理器复用。
- 新增 `test/web/mcp.test.ts`（2 例）：端点空配置、拒绝明文密钥、保存/刷新、响应脱敏。
- 全量基线：**282 passed / 1 skipped**（49 个测试文件 + 1 skip 的真实模型集成）；
  typecheck 与 `build:web` 通过。

## 2.1.1 — 2026-11-06（提示词工具清单改为代码发现，ADR-0011）

### 变更
- **清理 `modeling.system.md`**：删除硬编码的 `AVAILABLE TOOLS:` 清单（含
  `arxiv_search` / `web_search` / `webReader` 三个幽灵工具），换成
  `{{AVAILABLE_TOOLS}}` 占位符；WORKFLOW 的 `SEARCH (strongly recommended)` 改为
  离线的 `METHODS` 步，其余工具名统一改成「the available tools」。
  SETTING / RESPONSE FORMAT / PHILOSOPHY / MASTER PLAN FORMAT / IMPORTANT RULES
  **逐字不动**，由章节级基线断言守住。
- **代码发现工具清单**：新增 `packages/core/src/prompts/toolCatalog.ts`
  （`ToolDescriptor` / `renderToolList` / `injectToolList` / `toolDescriptorsFor`）与
  `packages/pi-runtime/src/toolDiscovery.ts`。内置工具读已安装 SDK 自己的
  `allToolNames` + `createToolDefinition(...).promptSnippet`，自定义工具读
  `buildCustomTools()` 的 `name/description`；SDK 内部路径变动时回落到代码常量，
  **绝不回落到提示词文本**。
- **注入点与会话同源**：`PiAgentRunner.run()` 先用发现结果过滤 `req.tools`，再用同一批
  名字生成清单注入 `systemPromptOverride`。提示词里的工具列表恒等于本次 session 的
  `options.tools`，SDK 升级或工具增减不再需要改提示词。
- **`OFFLINE_PLAN_POLICY` 去工具名化**：只保留「离线 + 首动作落盘 + 写完即停」，
  不再复述 `write` / `bash` / 幽灵检索工具，也不再自称「覆盖上面的工具说明」。
- 归档基线 `docs/legacy-prompts/expected-r2.json` / `modeling.py` 保持原样，历史证据链不删。

### 测试
- T1.2 快照由「全文相等」改为「除工具段与 WORKFLOW 外逐字相等」+ 反向断言
  （资产里不得出现工具名或工具清单式声明）；`tool-consistency` / `inline` 断言同步更新。
- 新增 `test/prompts/tool-discovery.test.ts`：发现结果覆盖角色白名单、含 SDK 独有
  `powershell`、不含幽灵工具、占位符替换、以及「注入的名字 == createOptions.tools」。
- ADR-0008 / MIGRATION-STATUS 加注后续修订说明；README 架构与文档表更新口径。
- 其余 `.md` 资产与 `RESULTS_CONTRACT` / `WORKSPACE_DISCOVERY_POLICY` 的工具名暂未清理，
  可按同一占位符机制逐步接入。

## 2.1.0 — 2026-11-06（一道题一个工作区 · 多 runtime 隔离，ADR-0010）

### 变更
- **目录契约**：工作区（题目）只保存 `inputs/` 与 `workspace.json`，每次运行写入
  `~/.solvex/workspaces/{id}/runs/{runId}/`（UUID 唯一），内含完整四阶段产物、
  `events.jsonl` 与 `runtime.json`。旧 `~/.solvex/sessions/{id}/` 与 `POST /api/run`
  保持只读/写入兼容，由 `listAllRuns()` / `findRun()` 统一索引，不迁移不删除。
- **允许并行运行**：移除 `POST /api/workspaces/:id/run` 的 409 与 `starting` 去重。
  每个 run 独享目录、EventBus、AbortController、阶段快照、事件日志与 ZIP；
  停止/回放/下载一个 run 不影响其他 run。工作区输入在启动瞬间快照进该 run。
- **runtime 配置快照**：启动可传白名单覆盖（模型分档 / thinking / scopedModels /
  concurrency / strict / persistThinking），合并后的生效配置写入 `runtime.json`。
  `sanitizeOverrides()` 丢弃未知字段、非法档位与疑似凭据；快照不含任何密钥。
  历史 run 的配置不再被后续全局设置改动影响，可对比、可复现。
- **API**：新增 `POST|GET /api/workspaces/:id/runs`、
  `GET /api/workspaces/:id/runs/:runId`（跨工作区 404）、
  `GET /api/runs/:id`、`GET /api/runs/:id/runtime`；旧 `/run`、`/api/sessions`
  与 14 个端点保持兼容。
- **前端对齐**：运行记录显示每次运行的 runtime 摘要与实时状态；「新建运行」在任何
  时候可用；「停止本次运行」只作用于选中 run；切换 run 重置 transcript/stages/usage；
  纯视图模型抽到 `src/client/runs.ts` 便于单测。

### 测试与工程
- 新增 `test/workspace-runs.test.ts`（目录/索引/快照/隔离）、
  `test/web/runs-view.test.ts`（前端视图模型）；改造 `test/web/workspaces.test.ts`
  覆盖并行启动、跨工作区 404、runtime 快照与旧 API 兼容。
- `vitest.config.ts` 限制 `maxWorkers: 2`、放宽 `testTimeout`，消除 Web 端点测试
  在高并行下冷启动导致的 SSE / 轮询偶发超时。
- `test/pi/modelsJsonContract.test.ts` 把 SDK 凭据存储隔离到临时目录，不再触碰
  `~/.pi/agent/auth.json.lock`。
- 全量基线：**262 passed / 1 skipped**，`typecheck` 与 `build:web` 通过。

## 2.0.3 — 2026-11-06（移除对外演示模式）

### 变更
- **删除公开演示模式**：`--fake` CLI 选项、`SOLVEX_FAKE` 环境变量、`ServerOptions.fake`
  与 `SessionRegistry` 的 fake 分支全部移除。CLI 与 WebUI 现在 100% 走真实模型运行时，
  用户不会再看到或误入合成数据的演示流程。
- 未知 CLI 选项不再被静默忽略，而是明确报错，避免旧命令误触发真实模型调用。
- `FakeAgentRunner` 保留为**内部测试实现**：测试通过
  `installFakeRunner()` 对 `SessionRegistry.prototype.runner` 做 spy 注入，产品代码不再有任何开关。
- CLI 端到端测试改为验证正常模式的参数解析、`inspect` / `validate` 只读命令与
  「演示开关及旧环境变量均被拒绝」；四阶段流程覆盖仍由 `test/flow` 与 `test/web` 承担。
- 清理 README / WebUI 使用说明中的演示命令；历史 benchmark 与迁移状态文档加注说明该模式已下线。

## 2.0.2 — 2026-11-05（结果证据链与工作区发现，ADR-0009）

### 修复
- **真实数值被占位符抹掉**：模型产出 CSV 却没写 `results_summary.md` 时，旧兜底一律写
  `⚠ Not available.`，`aggregate()` 又只聚合摘要，导致 P4 把「计算已完成」误写成
  「数值计算未完成」。现在 `renderSummaryRetry()` 先补一次专门会话；仍缺失时
  `summarizeArtifacts()` 扫描目录，把文件名、CSV 表头/行数、数值列 min/mean/max
  写进兜底摘要与 `all_results_summary.md`。
- **写作角色看不到共享工作区**：`ROLE_TOOLS.writing` 新增
  `ls / find / grep / bash / python_execute`（review 仍严格只读）；`writingSystem()`
  运行时追加 `WORKSPACE_DISCOVERY_POLICY`，要求 ALL RESULTS 出现占位符时必须先检索
  `02_programming/` 再下结论。此前 P4 的 `read` 对目录返回 `EISDIR`，实测 7 次 read、0 次 CSV。
- **图片缺失**：`RESULTS_CONTRACT` 强制至少一张 PNG 与六段式摘要；`checkPythonDeps()`
  探测绘图依赖，`runPython()` 在 `ModuleNotFoundError` 时给出可执行安装指引，
  不再静默跳过。运行时需预装 `numpy/pandas/matplotlib`。
- 新增 `PLACEHOLDER_SUMMARY` critical 质量门；`validateRoleTools()` 继续保证白名单 ⊆ 真实工具。
- 逐字提示词资产与内联模板常量一字未改，所有策略均为运行时追加。

## 2.0.1 — 2026-11-05（工具契约修复，ADR-0008）

### 修复
- **P1 不落盘 `master_plan.md`**：逐字提示词把 `SEARCH` 放在 `WRITE` 之前，而
  `arxiv_search` / `web_search` / `webReader` 在 Pi SDK 中并不存在且从未注入 session，
  模型改用 `bash + curl` 模拟联网检索，超时后无限重试，永远走不到 WRITE 步骤。
- **arxiv 检索死循环**：从 `ROLE_TOOLS.modeling` 与 `buildCustomTools()` 移除三个
  占位检索工具；`PiAgentRunner` 现在默认注入 `customTools` 并按 `AVAILABLE_TOOLS`
  过滤未知工具，杜绝「声明了但没接线」的静默失效。
- 新增 `OFFLINE_PLAN_POLICY` 运行时执行策略（沿用 `HANDOFF_HINT` 的追加模式），
  明确禁止联网、要求以 `write` 作为首个动作；逐字提示词资产与内联模板常量保持不动，
  T1.2 / T1.5 快照继续成立。
- 新增 `test/prompts/tool-contract.test.ts` 等回归断言：白名单必须是运行时工具子集、
  modeling 不含幽灵检索工具、runner 必须注入 `customTools`。

## 2.0.0 — 2026-11-05（Pi SDK 重构）

### 破坏性变更
- 运行时由 Python 自研 Agent Loop 全面切换到 TypeScript + `@earendil-works/pi-coding-agent@1.5.0`（精确锁定）。
- 删除 `ToolCallAgent` / `llm.py` / `ToolCollection` / `compact.py` / `FlowFactory`；四阶段编排改为 `@solvex/core` 状态机 + 并行 DAG。
- 环境要求 Node ≥ 22.19（`.nvmrc` = 22.20.0）。

### 新增
- **并行编排（D2）**：无依赖即并行，`--concurrency N`（默认 3，`=1` 等价旧串行）；屏障、失败隔离、取消传播、`writablePrefixes` 写安全。
- **WebUI 2.0 整体重写**：模型配置中心、思考过程视图、运行阶段 DAG 时间线、顶部实时用量条；14 个 API 端点 + SSE `Last-Event-ID` 续传 + 刷新回放。
- `SolveXEvent` v1.1：12 类结构化事件；`eventBridge` 转发 Pi 原生 `thinking_*` / `turn_*` / `tool_*` / `usage` / `lifecycle`。
- 结构化 `handoff.json` 双轨兼容（D3）、`--strict` 质量门（D4）、按阶段模型分档与 thinking 档位裁剪（D5）。
- CLI 新增 `serve` / `inspect` / `validate` / `--concurrency` / `--strict` / `--fake`；Web 上传改为标准 multipart（修复旧版 JSON Content-Type bug）。
- 凭据脱敏（R13）、`models.json` `$VAR` 插值、路径逃逸与越界写入拦截（R5/R11）。

### 保留
- 四阶段流程编排模式与 workspace 目录契约 100% 兼容。
- 提示词资产逐字搬运（10 个 `.py` 常量 + 5 段内联），仅 R-2 工具名白名单替换；`docs/legacy-prompts/` 完整归档。
- CLI `-p/-d/-r/--from-model/-w` 与旧版 1:1 对应；旧 4 个 Web 端点保持兼容。

### 测试
- 218 passed / 1 skipped（真实模型集成需 `PI_TEST_MODEL`）；`npm run check` 全绿。
- 23 个旧管线问题逐条回归结论见 `docs/regression-report.md`。
