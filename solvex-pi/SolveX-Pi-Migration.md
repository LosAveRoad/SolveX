# SolveX → Pi SDK 迁移设计文档（Migration Design）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | **v1.1**（已确认决策 / 并行编排 / WebUI 2.0 规格） |
| 日期 | 2026-11-04（v1.1 修订） |
| 源项目 | [LosAveRoad/SolveX](https://github.com/LosAveRoad/SolveX)（Python，基于 OpenManus 概念） |
| 目标运行时 | [Pi](https://pi.dev/) 官方 TypeScript SDK — `@earendil-works/pi-coding-agent`（**D1 已确认**） |
| 产品形态 | **带 WebUI 的 CLI 工具**（CLI 为主入口，WebUI 为同源可选界面，共用一套编排引擎；**WebUI 大幅升级为 2.0**） |
| 迁移原则 | **只保留「提示词」与「流程编排模式」**，其余运行时、Agent 循环、工具层、模型层、服务层全部替换 |
| 决策状态 | D1 / D2 / D6 已确认；D3 / D4 / D5 已给出推荐默认并逐项展开解释（§9），按推荐执行 |
| 配套文档 | `SolveX-Pi-Migration-Plan.md`（可执行实施计划，v1.1 同步更新） |

---

## 0. 执行摘要

**结论：迁移可行，且能顺带解决旧架构的大部分固有缺陷，但有一个必须先接受的架构前提——Pi 刻意不提供「多 Agent 编排」和「工作流引擎」。**

Pi 官方文档明确写明：`Pi ships with powerful defaults but skips features like sub-agents and plan mode`，并列出 `No sub-agents`、`No plan mode`、`No built-in to-dos`。因此「用 Pi SDK 来编排」的正确含义是：

> **由我们自己的 TypeScript 编排层，调用 Pi SDK 的 `createAgentSession()` 为每一阶段创建独立会话；编排层负责阶段推进、产物交接、评审循环、重试、事件广播。Pi 只负责单会话内的 Agent Loop、工具调用、模型接入、上下文压缩与会话持久化。**

这恰好与本次迁移的诉求吻合：旧项目里 `SolveXFlow`（四阶段管线）本来就是自研编排层，而 `ToolCallAgent` / `ReActAgent` / `LLM` / `ToolCollection` / `compact.py` 都是自研的 Agent 运行时——**这些自研运行时正是要被 Pi SDK 替换掉的部分**。换言之，本次重构是「换掉下半身、保留上半身」，边界非常干净。

四个最重要的收益：

1. **删掉约 60% 的自研运行时代码**：`app/llm.py`(29KB)、`app/agent/*`(约 40KB)、`app/tool/*`(约 150KB)、`app/service/compact.py`、自研 `Memory`/`Message` schema 全部由 Pi 接管。
2. **多模型供应商开箱即用**：Pi 内置 15+ providers（Anthropic / OpenAI / Google / Azure / Bedrock / Mistral / Groq / OpenRouter / Ollama / DeepSeek 兼容端点等），不再需要 `config.example-*.toml` 七份配置模板和 `app/bedrock.py`。
3. **上下文压缩、重试、会话树、流式事件由框架保证**：旧项目 `docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md` 记录的 F1/F2（超长响应、压缩后质量下降）等基础设施问题，可用 Pi 内置 compaction + `agent_settled` + 阶段隔离会话直接缓解。
4. **WebUI 2.0 的三大能力有原生数据源**：Pi 的 `ModelRuntime.getAvailable()`、`thinking_*`、`turn_*`、`usage` 事件与 7 档 thinking level，让「类 Pi 的模型配置体验 / 思考过程 / 运行阶段」不必靠轮询或猜测，直接桥接即可（§3.6、§10）。

**v1.1 已确认的四件事**：

1. **D1**：只使用 Pi 官方 TypeScript SDK `@earendil-works/pi-coding-agent`——不是 `pi-agents` 工作流包，也不是第三方 orchestrator。§3.5 的对比保留作为决策依据，结论已锁定。
2. **D2**：**无依赖即并行**——P2 的 N 个模型实现、N 个评审各自并行，仅在有依赖处设屏障；并发上限可配（`--concurrency` / Web 滑块），`concurrency=1` 等价旧版串行。见 §4.4.1、§10.5.2。
3. **WebUI 大幅升级为 2.0**：必须具备 ① 类 Pi 的模型配置体验（模型选择 / thinking 档位 / 按阶段分档 / 凭据与自定义端点）、② 思考过程显示、③ 运行阶段显示。前端整体重写而非打补丁，完整规格见 **§10**。
4. **D6**：不做、不发布 `pi-package/`；提示词只保留 `.md` 一份真源。

D3 / D4 / D5 已按用户要求在 §9 逐项展开背景、选项对比、推荐理由与影响面；三者均按推荐默认执行，如需改变可直接指出。

---

## 1. 目标、约束与非目标

### 1.1 目标

| # | 目标 | 验收口径 |
| --- | --- | --- |
| G1 | 保留全部有效提示词资产，语义与占位符不变 | 逐文件快照比对 + golden prompt 测试 |
| G2 | 保留四阶段编排模式（含评审/修订循环、resume、skip-to-writing） | 阶段状态机行为与旧版逐项对齐 |
| G3 | 底层 Agent 运行时 100% 由 Pi SDK 驱动 | 仓库中不再存在自研 LLM 调用 / Agent Loop / 工具集合 |
| G4 | 产品仍是「带 WebUI 的 CLI 工具」 | `solvex run` 与 `solvex serve` 两个入口共用同一 core |
| G5 | 输出目录结构与产物文件名保持兼容 | 旧 session 的 ZIP 可被新代码读取，反之亦然 |
| G6 | 修复旧版 23 个已知缺陷中的架构性根因 | 见 §8 验收基线 |
| G7 | 无依赖阶段自动并行，且并行不破坏产物一致性 | 依赖图 + 屏障单测；`concurrency=1` 与串行结果逐字节一致 |
| G8 | WebUI 支持类 Pi 的模型配置体验 | `GET /api/models` + 配置中心，可切模型 / thinking 档位 / 按阶段分档 / 自定义端点 |
| G9 | WebUI 实时显示**思考过程**与**运行阶段** | `thinking_*` 与 `stage` 事件驱动；刷新页面后可完整回放 |

### 1.2 硬约束

- **提示词是资产、不是代码**：迁移时以「原文搬运 + 变量占位符替换」为主，禁止顺手改写语义（旧提示词里包含大量踩坑后加的规则，如「不要编造数字」「先写正文最后写摘要」「每个 response 只调一个工具」）。
- **文件系统是阶段间唯一交接契约**：旧架构靠 `workspace/` 下的文件传递数据（`master_plan.md` → `results_summary.md` → `all_results_summary.md` → `main.tex`），这个模式必须保留——它是「可复现、可人工审阅」设计原则的载体。
- **CLI 参数保持兼容**：`--problem/-p`、`--data/-d`、`--resume/-r`、`--from-model`、`--skip-to-writing/-w`。
- **Web API 保持兼容**：`POST /api/run`、`GET /api/stream/{id}`(SSE)、`GET /api/download/{id}`、`GET /api/sessions`。
- **WebUI 2.0 为硬目标**：模型配置、思考过程、运行阶段三项必须可见可操作，不能只做「日志流」（§10）。
- **并行不得破坏文件系统交接契约**：共享文件 `all_results_summary.md` 只能由 P3 聚合生成，任何 LLM 会话不得写；并行任务按 `taskId` 限定可写前缀（§4.4.1）。
- **凭据不出后端**：API Key 不回传前端、不写日志、不进事件回放文件（§10.9）。
- **Pi 原生 thinking 事件全量透传**：`thinking_start/_delta/_end` 必须桥接到 SSE，前端按 `contentIndex` 重建并以 `*_end` 权威值覆盖（§4.6、§10.4）。

### 1.3 非目标（本次不做）

- 不改变业务领域：仍是数学建模竞赛（MCM/ICM 类）问题 → 模型 → 代码 → 图 → LaTeX 论文。
- 不引入**外部**编排引擎 / 分布式队列 / 事件溯源框架；「无依赖即并行」由 core 内的轻量 DAG + 屏障实现（§4.4.1、§10.5.2），不新增第三方依赖。
- 不做多租户、鉴权、云端托管。Pi 官方文档明确：SDK 运行在宿主进程权限下，**不是安全沙箱**；WebUI 暴露公网前必须自行加隔离（见 §7 R5）。
- 不产出 / 发布 `pi-package/`（D6 已确认）；提示词只以 `.md` 单一真源供 SDK 注入。
- 不迁移旧仓库的 `tests/competition/*.pdf|zip` 大文件（约 9MB）到新仓库，改为 fixture 引用。

---

## 2. 现状盘点（源项目）

### 2.1 代码地图与规模

通过 GitHub API 取得完整文件树（`main` 分支，仓库约 10 MB，其中约 9 MB 是测试数据集）。代码层分布：

| 层 | 路径 | 规模 | 处置 |
| --- | --- | --- | --- |
| **提示词（保留）** | `app/prompt/*.py` 共 10 个文件 | 约 33 KB | **迁移** → `packages/core/src/prompts/` |
| **流程编排（保留模式）** | `app/flow/solvex_flow.py` (21.9 KB)、`planning.py` (18.3 KB)、`base.py`、`flow_factory.py` | 约 43 KB | **重写** → `packages/core/src/flow/` |
| CLI | `run_flow.py` (5.5 KB)、`main.py` | 约 6 KB | 重写 → `apps/cli` |
| WebUI | `api.py` (5.7 KB)、`static/{index.html,app.js,style.css}` | 约 11 KB | 重写 → `apps/web` |
| 工作区 | `app/workspace.py` (3.8 KB) | 3.8 KB | 重写（契约不变） → `packages/core/src/workspace/` |
| Agent 运行时（丢弃） | `app/agent/base.py`、`react.py`、`toolcall.py`(11 KB)、`manus.py`、`mcp.py`、`sandbox_agent.py`、`browser.py` + 6 个细分 agent | 约 40 KB | **删除**，由 Pi SDK 接管 |
| LLM 抽象（丢弃） | `app/llm.py` (29.7 KB)、`app/bedrock.py` (13 KB)、`app/config.py` (13 KB) | 约 56 KB | **删除**，由 `pi-ai` / `models.json` 接管 |
| 工具层（丢弃/重写） | `app/tool/` 约 30 个文件（含 `python_execute`、`str_replace_editor`、`web_search`、`arxiv_search`、`browser_use_tool`、`chart_visualization`、sandbox 系列、MCP） | 约 150 KB | **大幅删除**；仅保留必要的自定义工具，见 §5.5 |
| 上下文压缩（丢弃） | `app/service/compact.py` (7.6 KB) | 7.6 KB | **删除**，Pi 内置 compaction |
| Schema（丢弃） | `app/schema.py` (5.7 KB) | 5.7 KB | **删除**，改用 TypeBox / zod 定义产物契约 |
| 配置 | `config/config.example*.toml` 共 8 份 | 约 15 KB | **删除**，改 `models.json` / 环境变量 |
| 已知缺陷清单 | `docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md` (18.6 KB) | 18.6 KB | **转为验收基线** |

> 观察：旧仓库 ~85% 的代码是「Agent 运行时 + 工具 + 模型适配」，只有 `app/prompt/` 与 `app/flow/solvex_flow.py` 是真正的业务资产。这正是本次重构的价值所在。

### 2.2 运行时架构

```
run_flow.py (CLI)  ─┐
                    ├─→ FlowFactory.create_flow(SOLVEX, agents={modeling, programming, writing})
api.py (FastAPI) ───┘         │
                              ▼
                    SolveXFlow.execute(input_text, workspace, resume_from, skip_to_writing)
                              │  _emit(queue, type, message) → stdout / SSE
                              ▼
        ┌───────────────────────────────────────────────┐
        │ Phase 1  ModelingAgent.run(modeling_prompt)     │ → 01_modeling/master_plan.md
        │ Phase 2  for each "## Model N:" section:        │
        │   ProgrammingAgent.run()  ×≤2 (revision loop)   │ → 02_programming/model_n/*
        │   _validate_model_output()  [质量门]            │
        │   ModelingAgent.run(REVIEW_PROMPT)              │ → 01_modeling/*_review.md
        │   if NEEDS_REVISION → ProgrammingAgent.run(fix) │
        │ Phase 3  聚合 all_results_summary.md            │
        │ Phase 4  WritingAgent.run(write_prompt)         │ → 04_paper/main.tex
        └───────────────────────────────────────────────┘
                              │
        Agent.run() = ReActAgent 循环 (think → act → max_steps)
            ├─ LLM.ask_tool()  (OpenAI 兼容 / Anthropic / Bedrock / Ollama ...)
            ├─ ToolCollection.execute()  (python_execute / str_replace_editor / terminate ...)
            ├─ Memory (最多 100 条) + compact_agent_memory()  (>80K tokens 时摘要)
            └─ terminate 工具 → AgentState.FINISHED
```

### 2.3 提示词资产清单（**核心保留项**）

| 文件 | 导出常量 | 用途 | 是否在 SolveXFlow 主链路 | 迁移优先级 |
| --- | --- | --- | --- | --- |
| `app/prompt/modeling.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT`、`REVIEW_PROMPT` | 建模专家：检索文献、设计多模型 Master Plan；评审实现结果 | **是**（Phase 1 + Phase 2 评审） | P0 |
| `app/prompt/programming.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | 数值计算程序员：实现模型、跑实验、出图、写 `results_summary.md` | **是**（Phase 2） | P0 |
| `app/prompt/writing.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | 学术写作：严格依据结果写 20–30 页 LaTeX 论文 | **是**（Phase 4） | P0 |
| `app/prompt/visualization.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | 出版级图表 + 图目录（写 `03_figures/`） | 否（有 `VisualizationAgent`，但当前 flow 未调用；出图已内嵌在 programming 提示词中） | P1（保留为可选 stage / skill） |
| `app/prompt/planning.py` | `PLANNING_SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | `PlanningFlow` 用，配合 `PlanningTool` | 否（另一条 flow） | P2（归档，不迁移到主链路） |
| `app/prompt/manus.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | OpenManus 通用助手 | 否 | P2（丢弃） |
| `app/prompt/mcp.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT`、`TOOL_ERROR_PROMPT`、`MULTIMEDIA_RESPONSE_PROMPT` | MCP Agent | 否 | P2（丢弃；Pi 原生支持 MCP） |
| `app/prompt/swe.py` | `SYSTEM_PROMPT` | SWE-agent 风格命令行编辑 | 否 | P2（丢弃；Pi 内置 edit/bash） |
| `app/prompt/toolcall.py` | `SYSTEM_PROMPT`、`NEXT_STEP_PROMPT` | `ToolCallAgent` 兜底提示词（"You are an agent that can execute tool calls"） | 否 | 丢弃（Pi 自带极简 system prompt） |
| `app/prompt/browser.py` | — | 浏览器 Agent | 否 | 丢弃（Pi 生态用 MCP/扩展） |

**主链路真正生效的只有 3 个文件、7 个常量**（另加 visualization 为潜在第 4 个）。这是迁移的最小资产集。

**提示词中必须原样保留的关键规则**（都是旧版踩坑后的修复，见 §2.7）：

- `modeling.py`：`## Model N:` 分节格式（被 `_parse_models()` 正则解析）、"每个模型 section MUST start with '## Model N:'"、写入绝对路径后方可 terminate。
- `programming.py`：`VERIFICATION_RESULT: SATISFIED / NEEDS_REVISION` 标记（被 flow 字符串匹配）、`results_summary.md` 的 6 个固定小节、figures 规格（Agg 后端、dpi=300、`figures/` 子目录）、"每次 python_execute 必须自带 import + 计算 + print"（无持久变量进程）、"保存 .py 文件而不只是 print 输出"。
- `writing.py`：**只用给定数字、禁止编造**、插入每一张图、交叉核对异常数值（US 28 vs 126 奖牌）、两模型表相同要如实说明、分多次编辑写长文。
- `REVIEW_PROMPT`：结尾恰好一个 `VERIFICATION_RESULT` 标记 + `## Issues Found:` / `## Fix Instructions:` 结构、数值合理性检查（首枚奖牌概率总和 ~2–5 而非 60）。
- `solvex_flow.py` 内联的 `write_prompt`：**先写正文、最后写摘要**（解决摘要与结论矛盾）、图片相对路径 `../02_programming/model_N/figures/xxx.png`、路径中不加单引号。

> ⚠️ 注意：SolveXFlow 的 Phase 1/2/4 还有 **5 段内联拼装的 prompt**（`modeling_prompt`、`retry_prompt`、`programming_prompt`、`fix_prompt`、`write_prompt`），它们散落在 `solvex_flow.py` 而非 `app/prompt/`。这些同样属于「提示词资产」，必须与 `app/prompt/` 一起迁移，否则编排模式无法复现。完整清单见 **附录 A**。

### 2.4 流程编排模式（**核心保留项**）

`SolveXFlow.execute()` 是一个**可恢复的四阶段状态机**，阶段间通过文件交接、通过文本标记决策：

| 阶段 | 输入 | 执行者 | 产物 | 控制逻辑 |
| --- | --- | --- | --- | --- |
| **P1 Master Plan** | 问题文本 + `data/` 文件清单 | modeling agent | `01_modeling/master_plan.md` | 失败则重试一次（改写更强硬的 `retry_prompt`）；两次仍无文件则抛错。可被 `resume_from>0` / `skip_to_writing` 跳过 |
| **P2 实现 + 评审** | Master Plan 按 `## Model N:` 切分 | programming agent → modeling agent(评审) | `02_programming/model_n/{*.py,*.csv,figures/*.png,results_summary.md}`、`01_modeling/model_n_review.md` | 对每个模型：① 最多 2 轮实现，依据 `VERIFICATION_RESULT` 决定是否带上一轮摘要重新实现；② 缺失 `results_summary.md` 时生成带 ⚠ 标记的结构化兜底；③ `_validate_model_output()` 质量门（文件存在、体积、`<think/>` 残留、概率和 >50、>0.95 占比 >30%、无图）；④ 评审前快照 `master_plan.md`、评审后若被篡改则还原；⑤ 评审为 `NEEDS_REVISION` 时，截取 `## Fix Instructions:` 段落发起定向修复 |
| **P3 聚合** | 各模型 `results_summary.md` + 图清单 | 纯代码（无 LLM） | `02_programming/all_results_summary.md` | 拼接所有结果与图目录 |
| **P4 论文** | Master Plan + 聚合结果 + 图清单 | writing agent | `04_paper/main.tex` | 单次 prompt 内含全部上下文；要求分多次编辑、最后写摘要 |

**辅助控制**：
- `resume_from`（1-based）：跳过已完成模型，支持从中断处续跑；CLI `--from-model` 会自动探测首个缺 `results_summary.md` 的模型。
- `skip_to_writing`：跳过 P1/P2，直接用已有产物写论文。
- `max_iterations=3`（构造参数，实际未充分使用）。
- 超时：CLI `asyncio.wait_for(..., 7200)`，Web `3600`。
- 事件：`_emit(queue, type, message)`，`type ∈ {status, step, done, info, warn}`，同时写彩色 stdout 与 SSE 队列；Web 端补 `complete` / `error` / `ping`。

**决策协议（脆弱点）**：所有阶段间判定都靠**在自然语言输出里找固定字符串**（`VERIFICATION_RESULT: SATISFIED`、`## Model N:`、`## Fix Instructions:`）。这是旧版 B2/E4/D4 等缺陷的根源之一，迁移时应升级为结构化 handoff（见 §6 ADR-03），但**必须保留对旧标记的兼容读取**，以保证「编排模式不变」。

### 2.5 产物契约（workspace 目录）

`app/workspace.py` 定义，CLI 与 Web 共用，**必须保持兼容**：

```
~/.solvex/sessions/{session_id}/        # session_id 形如 "0423-b8a2" 或 uuid[:8]
├── 00_problem/problem.md               # 原始问题文本
├── data/                               # 上传/指定的数据文件（CSV/XLSX/ZIP）
├── 01_modeling/
│   ├── master_plan.md                  # P1 产物，含 "## Model N: ..." 分节
│   └── {model_dir_name}_review.md      # P2 评审产物
├── 02_programming/
│   ├── model_1/                        # model_dir_name = "Model 1".lower().replace(" ","_")
│   │   ├── *.py  *.csv  results_summary.md
│   │   └── figures/*.png
│   ├── ...
│   └── all_results_summary.md          # P3 产物
└── 04_paper/main.tex                   # P4 产物
```

注意：README 里写的 `03_figures/` 与实际代码不一致——实际出图落在 `02_programming/model_n/figures/`，`_validate_model_output()` 也检查该路径。迁移以**代码为准**，并在新文档中修正这一处文档漂移。

### 2.6 CLI 与 WebUI 接口

**CLI**（`run_flow.py`）：

| 参数 | 行为 |
| --- | --- |
| `--problem/-p FILE` | 读取 `.md/.txt` 问题文本 |
| `--data/-d PATH` | 数据目录或文件 |
| `--resume/-r ID` | 续跑 `~/.solvex/sessions/ID`，跳过 `prepare_workspace()`（**不清理已有产物**） |
| `--from-model N` | 从第 N 个模型续跑；未指定则自动探测 |
| `--skip-to-writing/-w` | 仅执行 P4 |
| 无参数 | 交互式 `input()` 读取问题 |

**Web API**（`api.py`，FastAPI + `sse_starlette`）：

| 端点 | 说明 |
| --- | --- |
| `POST /api/run` | multipart：`text` + `files[]`（单个 zip 自动解压）→ 返回 `{session_id}`；后台 `asyncio.create_task` 执行 |
| `GET /api/stream/{id}` | SSE，30s 无事件发 `ping`；收到 `complete`/`error` 关闭 |
| `GET /api/download/{id}` | 打包 workspace 为 ZIP |
| `GET /api/sessions` | 列出历史 session（扫描 `~/.solvex/sessions/`） |
| `GET /` + `/static/*` | 单页 UI：侧栏历史、输入框、进度流、结果卡片、下载按钮 |

> 已知缺陷：前端 `startRun()` 用 `Content-Type: application/json` 发送 `{text}`，而后端 `/api/run` 声明的是 `Form(...)`/`File(...)` multipart——**旧版 Web 上传路径实际是坏的**。迁移时必须修掉（见 §8 Q-Web）。

### 2.7 已知技术债务（迁移的验收基线）

仓库自带 `docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md`，记录了 2025 MCM Problem C 端到端测试暴露的 **23 个问题**，分 6 类：

| 类别 | 数量 | 代表问题 | 根因归属 |
| --- | --- | --- | --- |
| A 建模 Agent | 3 | A1 计划过于理想化（Neural CDE / Bayesian Tensor 但环境无 PyMC/PyTorch）；A2 评审时覆写 master_plan；A3 无时间预算，5 个模型跑不完 | 提示词 / 流程保护 |
| B 编程 Agent | 5 | B2 `results_summary` 自动兜底泄漏 `<think/>` 与原始工具输出；B3 预测数值量级错误（US 28.3 vs 实际 126）；B4 概率未校准（37 国 >0.99，总和 62） | 产物契约 / 质量门 |
| C 评审 Agent | 3 | C1 评审文件根本没生成；C2 没抓到 B4；C3 评审提示词太泛 | 决策协议 |
| D 写作 Agent | 5 | D1 抄错数值；D2 两模型表完全相同；D3 摘要与结论矛盾；D4 编造 MAE=2.1 等指标；D5 编造未实现模型的内容 | 提示词 / 上下文传递 |
| E 编排 | 4 | E1 1h 超时太紧；E3 阶段间无验证门；E4 兜底摘要污染 | **编排层（本次重点）** |
| F 基础设施 | 3 | F1 DeepSeek Reasoner 单次 80K tokens 导致下轮 BadRequest；F2 压缩后质量下降；F3 无文件保护 | **自研运行时（Pi 可解）** |

文档自述的核心结论：

> "Most issues trace back to **B5 (inconsistent results_summary format)** and **E3 (no validation gate)**."
> 根因链：`B3 ← B2 ← E4 → D1 ← D2`；`B4 ← A1 ← A3 → C2 ← C3`；`D4 ← B2`；`D3 ← F1`；`A2 ← F3`。

**这份清单直接转化为新架构的验收标准**（§8）：凡属 F 类的问题由 Pi SDK 消除，凡属 E 类的问题由新编排层的强类型契约 + 质量门消除，凡属 A/B/C/D 类的问题由「保留提示词 + 强化产物 schema」消除。

---

## 3. 目标技术栈：Pi SDK

### 3.1 Pi 是什么、不是什么

| Pi 提供 | Pi 不提供（需自建） |
| --- | --- |
| 单会话 Agent Loop（模型 ↔ 工具循环） | 多 Agent 编排 / 工作流引擎 |
| 内置工具 `read` / `write` / `edit` / `bash` / `grep` / `find` / `ls` | `python_execute` 这类领域工具 |
| 15+ 模型供应商、OAuth / API Key、`models.json` 自定义 provider | 业务级数值合理性校验 |
| 会话持久化（树形分支、compaction、导出 HTML） | 阶段间产物契约 / 质量门 |
| 渐进式上下文工程：`AGENTS.md`、`SYSTEM.md`、Skills、Prompt Templates、动态 context 注入 | 四阶段状态机、resume、skip-to-writing |
| 扩展（自定义工具、命令、事件拦截、UI）、MCP、Codemode | WebUI / SSE / ZIP 导出 |
| 四种运行模式：Interactive / Print / JSON / **SDK**（另有 RPC） | OS 级沙箱、权限边界 |

> 官方安全提示：*"Pi's tools and extensions run with the permissions of the Pi process... it does not sandbox tool calls."* WebUI 场景必须自行加容器/目录隔离（§7 R5）。

### 3.2 模式选型：为什么用 SDK 而不是 RPC / JSON / 子进程

| 模式 | 交互 | 是否适合本产品 | 判断 |
| --- | --- | --- | --- |
| Interactive TUI | 终端全屏 | ❌ | 我们是自有 CLI + WebUI，不复用 Pi TUI |
| Print (`pi -p`) | 一次性、只给最终文本 | ❌ | 无法拿到中间进度，无法做四阶段编排 |
| JSON (`pi --mode json`) | 单次运行的 JSONL 事件流 | ⚠️ 备选 | 事件结构完善，但**每次调用都是独立进程、结束即退出**，四阶段需反复 spawn，会话/工作区状态要自己串；适合「一次一阶段」的粗粒度集成 |
| RPC (`pi --mode rpc`) | 长进程双向控制，官方提供 `RpcClient.promptAndWait()` | ⚠️ 备选 | 适合非 Node 宿主；但我们是 Node/TS，多一层进程边界与协议维护成本 |
| **SDK（内嵌）** | `createAgentSession()` 直接拿 `AgentSession` | ✅ **选定** | 同一进程内可为每阶段创建独立 session、直接订阅事件、精确控制 `abort()/steer()`、共享 workspace 与配置；最贴合「用 SDK 来编排」 |

**结论**：`apps/cli` 与 `apps/web` 都直接内嵌 SDK；不启动 `pi` 子进程。JSON 事件流的**事件形状**仍作为我们 SSE 契约的设计参考（附录 C）。

### 3.3 SDK 关键 API（已核对官方文档与 typechecked 示例）

```ts
import {
  createAgentSession, SessionManager, DefaultResourceLoader, getAgentDir,
} from "@earendil-works/pi-coding-agent";

const loader = new DefaultResourceLoader({
  cwd,
  agentDir: getAgentDir(),
  systemPromptOverride: () => modelingSystemPrompt,     // 完全替换 system prompt
  appendSystemPromptOverride: () => [],                 // 阻止 APPEND_SYSTEM.md 追加
  additionalExtensionPaths: ["./extensions/solvex-tools.ts"],
  extensionFactories: [(pi) => { /* 内联扩展 */ }],
  // extensionFactories 亦可挂 createCodemodeExtension() / createMcpExtension()
});
await loader.reload();

const { session } = await createAgentSession({
  cwd,                                  // 决定工作区 / 资源发现 / 内置工具路径
  sessionManager: SessionManager.inMemory(),   // 或持久化（默认）
  resourceLoader: loader,
  tools: ["read", "write", "edit", "bash", "grep", "find", "ls"],
  // 还可显式给：model、thinkingLevel、scopedModels、modelRuntime、
  //            settingsManager、noTools、excludeTools、customTools
});

const unsubscribe = session.subscribe((event) => { /* 事件流 */ });
try {
  await session.prompt(taskPrompt);          // 运行结束才 resolve（含自动重试）
  const text = session.getLastAssistantText();
} finally {
  unsubscribe();
  session.dispose();                        // 中止工作、移除监听、释放扩展上下文
}
```

**Session 生命周期要点**：

- `session.prompt()` 会先处理扩展命令、展开 prompt template；运行期间再次 `prompt()` 必须显式选择 `steer()`（当前 turn 后插入）或 `followUp()`（本轮结束后排队），否则拒绝。
- `abort()` / `waitForIdle()` / `session.messages` / `session.model` / `session.systemPrompt`(只读) / `session.getActiveToolNames()`。
- `SessionManager` **是会话历史的唯一权威**；不要直接改 `session.agent.state.messages`。`AgentSessionRuntime` 提供 `newSession() / switchSession() / fork() / importFromJsonl()`，替换后需重新绑定订阅。
- 需要 `session.bindExtensions()` 才会触发扩展的 `session_start`（MCP server 在此连接）。

**事件（AgentSessionEvent，订阅获得）**：

| 事件 | 用途 |
| --- | --- |
| `message_update` + `text_start` / `_delta` / `_end` | 流式正文（`contentIndex`、`delta`、`content`；`text_end` 为权威值） |
| `message_update` + `thinking_start` / `_delta` / `_end` | ★ **思考过程**（WebUI 2.0 的数据源；`thinking_end.content` 为权威值） |
| `message_update` + `toolcall_start` / `_delta` / `_end` | 工具调用参数的流式增量 |
| `message_update.usage` | 累计 token / cost（`Usage.reasoning` 已含在 `output`，勿重复累加） |
| `message_end` | **权威完成消息**，覆盖此前所有增量拼接 |
| `turn_start` / `turn_end` | 一个 assistant turn（响应 + 其工具调用）的起止 → 阶段视图内层 |
| `tool_execution_start` / `_update` / `_end` | 工具执行生命周期（`toolCallId`、`toolName`、`args`、`result`、`isError`、`durationMs`） |
| `agent_start` / `agent_end` | 低层 agent run 起止；`agent_end` 之后**仍可能**自动重试/压缩重试/排队工作 |
| `agent_settled` | ✅ **阶段真正结束的判据**（`aborted` 字段） |
| `compaction_start` / `compaction_end` | 上下文压缩（替代自研 `compact.py`） |
| `auto_retry_start` / `auto_retry_end` | 自动重试 |
| `thinking_level_changed` / `session_info_changed` | thinking 档位 / 会话名变化 → WebUI 顶部状态条同步 |
| `queue_update` / `entry_appended` | 队列与扩展自定义会话条目 |

> `message_update.assistantMessageEvent` 的完整嵌套类型为 `start | text_start | text_delta | text_end | thinking_start | thinking_delta | thinking_end | toolcall_start | toolcall_delta | toolcall_end | done | error`，均通过 `contentIndex` 关联同一内容块。**delta 只用于实时显示，`*_end` 与 `message_end` 才是权威值**（附录 C）。

**扩展能力**：`pi.registerTool({ name, label, description, parameters: Type.Object({...}), execute })`、`pi.registerCommand()`、`pi.registerShortcut()`、`pi.registerFlag()`、`pi.on("tool_call" | "agent_start" | "session_start" | ...)`（可返回 `{block:true, reason}` 拦截）、`pi.appendEntry()`（会话持久化）、`ctx.ui.confirm/select/input/notify/setStatus/setWidget/custom`。工具参数用 TypeBox/JSON Schema，Pi 会做校验与宽松类型强制。

**资源体系**（用于承载提示词资产，见 §5.1）：

- **Skills**：目录 + `SKILL.md`（frontmatter `name` / `description` / `disable-model-invocation`），启动时只注入名称与描述，命中时才加载全文（渐进披露）。
- **Prompt Templates**：`prompts/*.md`，frontmatter `description` / `argument-hint`，文件名即 `/命令`，支持 `$1`、`$@`、`${1:-default}`。
- **Pi Packages**：`package.json` 的 `pi` 字段声明 `extensions` / `skills` / `prompts` / `themes`，可 `pi install npm:...` 或 `pi install git:...`；宿主提供的包（`@earendil-works/pi-*`、TypeBox）必须放 `peerDependencies`，不可放 `dependencies`。
- **Extensions 位置**：`~/.pi/agent/extensions/` 或项目 `.pi/extensions/`（后者需 project trust），热重载 `/reload`。

### 3.4 运行环境要求

| 项 | 要求 | 当前沙箱 | 动作 |
| --- | --- | --- | --- |
| Node.js | **≥ 22.19.0**（官方 README / npm 包均声明） | v22.13.1 | **需升级**（nvm / 安装器） |
| 包管理 | npm / pnpm / bun 均可 | npm 11.9.0 / pnpm 10.28.2 | OK |
| 安装 | `npm i @earendil-works/pi-coding-agent`（或 `pi.dev/install.sh` 装 CLI） | — | 锁版本，Pi 迭代很快 |
| 模型凭据 | `/login` 或 API Key 环境变量 / `models.json` | 旧项目 `config.toml` | 迁移为 `models.json` + env |

> ⚠️ Pi 包名历史上从 `@mariozechner/*` 迁到 `@earendil-works/*`，且 2026-10 移除了实验性 server/client 包。**所有方案必须锁定一个具体版本并核对导出符号**，不要照抄旧教程（见 §7 R1）。

### 3.5 编排方案选型（D1 / D2 均已确认）

| 方案 | 是什么 | 优点 | 结论 |
| --- | --- | --- | --- |
| **A. 自研 TS 编排层 + Pi SDK 多 session** | 本文方案 | 完全掌控四阶段、resume、质量门、并行屏障；提示词 1:1 保留；无额外依赖 | ✅ **D1 已确认采用** |
| B. `pi-agents` (npm) | Pi 的**扩展包**，用 JSON 树描述 workflow：`spawn / sequence / fork / join / loop`，运行为独立 pi 子进程 | 声明式、自带 loop/join/budgets | ❌ 它是「Pi 扩展」而非 SDK；通用图语义不贴合 SolveX 的「按 `## Model N:` 切分 + 文件交接」；子进程边界增加成本；0.1.0 早期版本 |
| C. `@groeponline/pi-agent-orchestrator` | 多 Agent 编排扩展：subagents / worktree / swarm / handoff / TUI dashboard | 结构化 handoff、并行、可观测性开箱即用 | ❌ 面向「代码库并行改造」；其 TUI dashboard 与我们要的自有 WebUI 重叠；引入重型第三方依赖 |

**D1 结论**：只用官方 SDK `@earendil-works/pi-coding-agent`，不引入 B/C。`@solvex/core` 是唯一编排层；**D2 的并行在 A 内部用轻量 DAG + 屏障 + 并发上限实现**，不引入外部编排引擎。B/C 仅作为 fork/handoff 思路的参考。

### 3.6 模型配置与 thinking 的 SDK 精确 API（WebUI 2.0 的依据）

以下均已核对官方文档与 typechecked 示例 `examples/sdk/{02-custom-model,09-api-keys-and-oauth,10-settings}.ts`：

```ts
import {
  createAgentSession, ModelRuntime, SettingsManager, SessionManager,
} from "@earendil-works/pi-coding-agent";

// ① 单例 ModelRuntime：整个进程共享一次 catalog / 凭据加载（不要每阶段重建）
const modelRuntime = await ModelRuntime.create({
  authPath:  "~/.solvex/auth.json",
  modelsPath: "~/.solvex/models.json",
});

// ② 列出「凭据可用」的模型 → 直接喂给 WebUI 的模型选择器
const available = await modelRuntime.getAvailable();          // ModelDescriptor[]
const opus = modelRuntime.getModel("anthropic", "claude-opus-4-5");

// ③ 运行时注入凭据（只进内存，不落盘）→ WebUI「临时 API Key」
await modelRuntime.setRuntimeApiKey("anthropic", "sk-...");

// ④ 每阶段按配置创建会话
const { session } = await createAgentSession({
  cwd, modelRuntime,
  model: byPhase.P1,                       // 按阶段分档（§10.3）
  thinkingLevel: "high",                  // off|minimal|low|medium|high|xhigh|max
  scopedModels: ["anthropic/...", "openai/..."],   // ≡ Pi 的 Ctrl+P 循环集
  settingsManager,
  sessionManager: SessionManager.inMemory(),
});

// ⑤ 设置读写
const settingsManager = SettingsManager.create(cwd);
settingsManager.setDefaultThinkingLevel("medium");
await settingsManager.flush();
const errors = settingsManager.drainErrors();
```

**关键配置面**（`settings.json` / `models.json`）：

| 项 | 字段 | 取值 / 说明 |
| --- | --- | --- |
| 默认模型 | `defaultProvider` + `defaultModel` | 不硬编码，由 `models.json` / 环境变量决定 |
| 默认思考档 | `defaultThinkingLevel` | `off / minimal / low / medium / high / xhigh / max`，默认 `medium` |
| 按模型档位 | `modelThinkingLevels` | 以 `provider/modelId` 为键覆盖 |
| 循环模型集 | `enabledModels` | 等价 `/scoped-models` + `Ctrl+P` |
| 隐藏思考块 | `hideThinkingBlock` | WebUI「隐藏思考」开关映射此语义 |
| 自定义端点 | `models.json → providers.{id}.{baseUrl, api, apiKey, models[]}` | `apiKey` 支持 `$ENV` / `${ENV}` 插值；`api` 如 `openai-completions` |
| 凭据优先级 | — | runtime `--api-key` > `auth.json` > `models.json.apiKey` > 环境变量 |
| 目录刷新 | `pi update --models` | 等价 WebUI 的 `POST /api/models/refresh` |

> **thinking 档位由模型能力裁剪**：Pi 只列出该模型支持的档位，WebUI 必须按所选模型过滤；不支持 reasoning 的模型自动降为 `off`。`Usage.reasoning` 已包含在 `output` 中，**汇总成本时不可重复累加**。

---

## 4. 目标架构

### 4.1 分层

```
┌──────────────────────────────────────────────────────────────┐
│ apps/cli  (solvex run)        apps/web (solvex serve, WebUI 2.0)│  ← 两个入口，同一 core
│  - 参数解析/彩色进度          - HTTP + SSE + 模型配置 + 静态 UI  │
│  - --resume/--from-model      - 阶段/思考/用量三视图 + ZIP       │
│  - --concurrency/--strict     - /api/run /api/stream /api/models │
└───────────────┬──────────────────────────┬───────────────────┘
                │                          │
                ▼                          ▼
┌──────────────────────────────────────────────────────────────┐
│ @solvex/core   「编排层」= 保留的资产，零 Pi 依赖，可纯单测      │
│  flow/      四阶段状态机、resume、skip、并发策略                 │
│  prompts/   ★ 迁移后的提示词（.md + 模板函数）                  │
│  contracts/ 产物 schema（TypeBox）：MasterPlan / ModelResult /   │
│             ReviewVerdict / PaperSpec / Handoff                 │
│  gates/     质量门（原 _validate_model_output 的强类型升级）     │
│  workspace/ 目录契约、session_id、ZIP、数据拷贝                  │
│  events/    EventBus：stage/thinking/usage/... → SSE + 回放    │
│  ports/     AgentRunner 接口（★ 唯一依赖倒置点）                 │
└───────────────────────────┬──────────────────────────────────┘
                            │ implements
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ @solvex/pi-runtime   「Pi 适配层」= 唯一接触 SDK 的地方          │
│  PiAgentRunner  createAgentSession + DefaultResourceLoader      │
│                 systemPromptOverride / tools 白名单 / 事件桥接    │
│                 超时·abort·agent_settled·dispose                 │
│  extensions/   自定义工具：python_execute / arxiv_search /        │
│                 web_search / chart_visualization（按需）          │
│  ModelRuntime  单例 + 模型/thinking 配置 + 事件桥接              │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
              @earendil-works/pi-coding-agent (SDK)
              pi-ai / pi-agent-core / pi-tui / TypeBox
```

**核心设计：`@solvex/core` 完全不 import Pi。** 编排层只依赖 `AgentRunner` 端口，测试时用 `FakeAgentRunner`（按脚本返回预置产物）跑完整四阶段，做到 RED-GREEN TDD 不依赖模型 API。这也是"保留编排模式"最可靠的落地方式——编排逻辑被锁在纯函数/状态机里，不会被 SDK 版本升级冲垮。

### 4.2 建议目录结构（pnpm monorepo）

```
solvex/
├── package.json                 # workspaces, engines.node >=22.19
├── pnpm-workspace.yaml
├── tsconfig.base.json
├── vitest.config.ts
├── packages/
│   ├── core/
│   │   ├── src/
│   │   │   ├── flow/{SolveXFlow.ts, scheduler.ts, dag.ts, stages.ts, state.ts, resume.ts}
│   │   │   ├── prompts/
│   │   │   │   ├── modeling.system.md      ← app/prompt/modeling.py SYSTEM_PROMPT
│   │   │   │   ├── modeling.next.md        ← NEXT_STEP_PROMPT
│   │   │   │   ├── review.md               ← REVIEW_PROMPT
│   │   │   │   ├── programming.system.md
│   │   │   │   ├── programming.next.md
│   │   │   │   ├── writing.system.md
│   │   │   │   ├── writing.next.md
│   │   │   │   ├── visualization.system.md
│   │   │   │   ├── inline/{plan.ts,implement.ts,revision.ts,fix.ts,paper.ts}
│   │   │   │   └── index.ts                # 模板渲染 + 快照测试
│   │   │   ├── contracts/{masterPlan.ts, modelResult.ts, verdict.ts, handoff.ts}
│   │   │   ├── gates/{validateModelOutput.ts, parseVerdict.ts, protectMasterPlan.ts}
│   │   │   ├── workspace/{index.ts, paths.ts, zip.ts, sessions.ts}
│   │   │   ├── events/{EventBus.ts, types.ts}
│   │   │   └── ports/{AgentRunner.ts, FakeAgentRunner.ts}
│   │   └── test/                            # golden fixtures（旧 session 产物副本）
│   └── pi-runtime/
│       ├── src/{PiAgentRunner.ts, config.ts, eventBridge.ts}
│       ├── extensions/{solvex-tools.ts, safety.ts}
│       └── models.json
├── apps/
│   ├── cli/src/{index.ts, args.ts, renderer.ts}
│   └── web/
│       ├── src/{server.ts, routes.ts, sse.ts, modelConfig.ts, stages.ts}
│       └── public/
│           ├── {index.html, app.js, styles.css}
│           └── modules/{store.js, stream.js, models.js, thinking.js,
│                       stages.js, artifacts.js}   # WebUI 2.0，无构建链
├── docs/
│   ├── migration-design.md      # 本文档（§10 = WebUI 2.0 规格）
│   ├── migration-plan.md        # 实施计划
│   ├── webui-2.0.md             # WebUI 使用说明（阶段 8 产出）
│   └── adr/*.md
└── fixtures/2025_C/             # 从旧 tests/competition 摘取的精简回归夹具
```

### 4.3 核心抽象

```ts
// packages/core/src/ports/AgentRunner.ts  —— 编排层唯一依赖
export interface RunRequest {
  role: "modeling" | "programming" | "writing" | "visualization";
  systemPrompt: string;          // 由 prompts/ 渲染
  task: string;                  // 由 inline/* 模板拼装
  cwd: string;                   // = workspace 根目录
  tools?: string[];              // 工具白名单
  maxTurns?: number;             // 替代旧 max_steps
  timeoutMs?: number;
  // ── v1.1 新增：并行 + 模型配置 ──
  taskId?: string;               // "P1" | "P2-IMPL:model_2" | ... 事件关联键
  phase?: 1 | 2 | 3 | 4;
  model?: ModelRef;              // { provider, id }，按阶段分档覆盖
  thinkingLevel?: ThinkingLevel; // off|minimal|low|medium|high|xhigh|max
  scopedModels?: string[];       // 该会话可循环切换的模型集
  writablePrefixes?: string[];   // 并行时限定可写路径前缀（R11）
  onEvent?: (e: SolveXEvent) => void;
}
export interface RunResult {
  text: string;                  // getLastAssistantText()
  artifacts: string[];           // 本次运行写出的文件（相对 cwd）
  usage: { input: number; output: number; cost?: number };
  settled: boolean;              // 是否等到 agent_settled
}
export interface AgentRunner {
  run(req: RunRequest, signal?: AbortSignal): Promise<RunResult>;
}
```

`PiAgentRunner`（适配层）职责：

1. 按 `role` 取提示词、工具白名单、模型覆盖（`scopedModels`：例如建模用强推理模型、编程用快模型）。
2. 构造 `DefaultResourceLoader`（`systemPromptOverride` + `appendSystemPromptOverride: () => []`），`await loader.reload()`。
3. `createAgentSession({ cwd, sessionManager: SessionManager.inMemory(), resourceLoader, tools, ... })`。
   - **一阶段一 session**：P1、每个 Model N 的实现、每个评审、P4 各自独立会话 → 天然隔离上下文，避免旧版 F2（压缩后质量下降）；同时保留 `sessionManager` 持久化选项以便 `solvex inspect <id>` 回看。
4. `session.subscribe()` 把 Pi 事件桥接成 `SolveXEvent`（`text_delta`→`info`、`tool_execution_*`→`step`、`agent_settled`→ 结束判定、`abort()` 处理超时）。
5. `await session.prompt(task)` → 收集 `getLastAssistantText()`、扫描 workspace 新增文件作为 `artifacts`；`finally { unsubscribe(); session.dispose(); }`。
6. 超时/取消：`AbortSignal` → `session.abort()` → `session.waitForIdle()`。

> **max_steps 的替代**：Pi SDK 没有暴露 `max_steps`。用扩展的 `pi.on("turn_end")` 计数 + 预算达阈值时 `session.abort()`，或在编排层用 `timeoutMs` + 产物检查双重约束。旧值：modeling 25 / programming 30 / writing 40，作为默认预算保留。

### 4.4 会话模型与阶段隔离

| 阶段 | 会话数 | 上下文内容 | 备注 |
| --- | --- | --- | --- |
| P1 | 1 | 问题文本 + 数据文件清单 | 失败重试复用同一 prompt、新建会话 |
| P2 实现 | 每模型 1（+修订 1） | 问题 + 数据 + **该模型分节**（不再塞整份 Master Plan） | 旧版已这么做，保留 |
| P2 评审 | 每模型 1 | 问题 + 该模型分节 + `results_summary.md` | **只读工具白名单**，从根上消除 A2/F3（覆写 master_plan） |
| P2 定向修复 | 按需 1 | 问题 + 代码目录 + `## Fix Instructions:` | 只改指定问题 |
| P4 | 1 | 问题 + Master Plan + 聚合结果 + 图清单 | 长文分多次编辑，靠 Pi 内置 compaction 而非自研 |

**关键改进**：评审会话用 `tools: ["read","grep","find","ls"]`（只读），不再需要旧版"快照 master_plan → 事后还原"的补丁式保护（旧 Task 3）。这是「保留编排模式、换掉实现」的典型例子：保护意图保留，实现手段升级。

#### 4.4.1 并行调度（D2 已确认：无依赖即并行）

依赖图（箭头即屏障，只有真正存在数据依赖处才串行）：

```
P1 单任务 ──barrier(master_plan.md)──▶ P2-IMPL fork N 个 Model N【并行】
      ──barrier(全部 results_summary.md + 质量门)──▶ P2-REVIEW fork N 个评审【并行】
      ──barrier(全部 *_review.md)──▶ P3 聚合（纯代码，非 LLM）
      ──barrier(all_results_summary.md)──▶ P4 单任务
```

| 维度 | 设计 |
| --- | --- |
| 并发上限 | `concurrency` 默认 3，CLI `--concurrency N` / Web 滑块可调 1..N；`=1` 等价旧版串行，用于回归对照 |
| 会话隔离 | 每个并行任务独立 `createAgentSession()` + 独立 `SessionManager.inMemory()`；事件带 `taskId`/`model` 标签，EventBus 汇聚后按 `taskId` 分发 |
| **写冲突根除** | 共享文件 `all_results_summary.md` **不再由任何 LLM 写入**，改由 P3 `aggregate()` 在屏障后确定性生成（顺带修 B5/D2）；`master_plan.md` 全程只读；每个 model 只写自己的 `02_programming/model_n/`；扩展 `tool_call` 按 `writablePrefixes` 拦截越界写入（R11） |
| 失败隔离 | 单个 model 失败不取消其他任务；屏障处汇总失败项，WebUI 提供「重试失败项」；单个任务的自动重试/压缩由 Pi 自己处理（`agent_settled` 判定） |
| 取消传播 | `POST /api/abort/{id}` → `AbortController` → 所有在跑 session 的 `abort()`；已落盘产物不损坏 |
| resume 语义 | 并行下 `--from-model N` 改为按「已完成 / 失败」状态跳过，而非按序号；已完成模型不重跑，失败与未完成项重新入队 |
| 成本护栏 | 全局 token / cost 预算（R7 / R14）；超预算发 `warn` 并停止派发新任务，已在跑任务允许收尾 |

`@solvex/core/src/flow/{scheduler.ts, dag.ts}` 是纯函数 + 状态机，**零 Pi 依赖**，用 `FakeAgentRunner` 即可 TDD 验证屏障、并发上限、失败隔离与取消传播（计划 T2.9）。

### 4.5 工具映射

| 旧工具 | 新实现 | 说明 |
| --- | --- | --- |
| `str_replace_editor` | Pi 内置 `write` / `edit` | 语义等价；提示词中的工具名需同步改写（见 §5.1 规则 R-2） |
| `python_execute` | 自定义扩展工具 `python_execute`（内部 spawn `python3` 并捕获 stdout），或直接用内置 `bash` 执行 `python3 script.py` | **建议保留自定义工具**：旧提示词明确依赖"每次调用自带 import + 计算 + print、变量不持久"的语义，封装成工具可 1:1 复现 |
| `terminate` | 删除 | Pi 自行判断结束；`agent_settled` 即终止信号 |
| `bash` | Pi 内置 `bash` | — |
| `arxiv_search` / `tavily_search` / `web_search` / `webReader` | 自定义扩展工具，或接入 **Pi 内置 MCP** | 建模阶段强依赖文献检索；优先 MCP 化，减少自维护代码 |
| `chart_visualization` (TS/Python 图表) | 删除（旧提示词已让 programming agent 用 matplotlib 出图） | 避免双轨 |
| `browser_use_tool` / `computer_use_tool` / `crawl4ai` / sandbox 系列 / Daytona | 删除 | 主链路未使用 |
| `PlanningTool` | 删除（或降级为 Pi 的 prompt template + TODO 文件） | 属于 `PlanningFlow`，不在主链路 |
| `ask_human` / `CreateChatCompletion` / `mermaid_diagram` | 删除 | — |
| `MCP` (`app/mcp/server.py`, `app/tool/mcp.py`) | Pi 内置 MCP（`createMcpExtension()`）+ `models.json` | SDK 会话默认不加载 MCP 扩展，需显式加入 `extensionFactories` 并 `session.bindExtensions()` |

> 工具白名单按角色收紧，是本次迁移顺带获得的安全与质量收益：
> modeling = `read, grep, find, ls, bash, python_execute, arxiv_search, web_search, webReader, write, edit`；
> programming = `read, write, edit, bash, python_execute`；
> **review = `read, grep, find, ls`（只读）**；
> writing = `read, write, edit`。

### 4.6 事件与 SSE 契约

**v1.1 完整契约**。保留旧事件类型（CLI 渲染不变），补齐 WebUI 2.0 所需的阶段、思考、用量、模型四类结构化事件：

```ts
// packages/core/src/events/types.ts
export type Phase = 1 | 2 | 3 | 4;
export type ThinkingLevel = "off"|"minimal"|"low"|"medium"|"high"|"xhigh"|"max";
export type TaskId = string;   // "P1" | "P2-IMPL:model_2" | "P2-REVIEW:model_2" | ...

export type SolveXEvent =
  // ── 兼容旧版（CLI 彩色渲染不变）──
  | { type: "status"|"step"|"done"|"info"|"warn"; message: string;
      phase: Phase; model?: string; taskId?: TaskId; ts: number }
  | { type: "artifact"; path: string; phase: Phase; model?: string; taskId?: TaskId }
  | { type: "complete"; result: RunSummary }
  | { type: "error"; message: string; phase?: Phase; taskId?: TaskId }

  // ── 运行阶段（外层，core 权威发出）──
  | { type: "stage"; op: "upsert"|"remove"; node: StageNode; ts: number }
  | { type: "barrier"; id: string; state: "waiting"|"released";
      completed: number; total: number; ts: number }

  // ── 思考 / 输出 / 工具（内层，eventBridge 转发 Pi 事件）──
  | { type: "thinking"; state: "start"|"delta"|"end"; taskId: TaskId;
      blockId: string; contentIndex: number; delta?: string;
      content?: string; redacted?: boolean; ts: number }
  | { type: "output"; state: "delta"|"end"|"final"; taskId: TaskId;
      blockId: string; contentIndex: number; delta?: string;
      content?: string; message?: unknown; ts: number }
  | { type: "tool"; taskId: TaskId; toolCallId: string; name: string;
      state: "start"|"update"|"delta"|"end"; args?: unknown;
      partialResult?: unknown; result?: unknown; isError?: boolean;
      durationMs?: number; ts: number }
  | { type: "turn"; taskId: TaskId; state: "start"|"end"; turn: number; ts: number }

  // ── 模型 / 用量 / 生命周期 ──
  | { type: "model"; taskId?: TaskId; provider: string; model: string;
      thinkingLevel?: ThinkingLevel; ts: number }
  | { type: "usage"; taskId?: TaskId; input: number; output: number;
      cacheRead: number; cacheWrite: number; totalTokens: number;
      cost: number; cumulative: boolean; ts: number }
  | { type: "lifecycle"; taskId: TaskId;
      state: "agent_start"|"agent_end"|"agent_settled"|"compaction"|"auto_retry"|"aborted";
      detail?: string; ts: number }
  | { type: "ping"; ts: number };
```

`StageNode`（右侧阶段时间线的数据模型，详见 §10.5.3）：

```ts
export type StageNode = {
  id: string; label: string; phase: Phase; kind: "stage"|"task";
  state: "pending"|"queued"|"running"|"done"|"failed"|"aborted"|"skipped";
  parentId?: string; dependsOn: string[]; taskId?: TaskId; model?: string;
  role?: "modeling"|"programming"|"writing";
  startedAt?: number; endedAt?: number; turns?: number; toolCalls?: number;
  usage?: { input: number; output: number; cost: number }; thinkingMs?: number;
  verdict?: "satisfied"|"needs_revision"|"unknown"; issues?: Issue[];
};
```

**契约要点**：

- **双层阶段**（ADR-14）：外层 `stage` 由 `SolveXFlow`/`scheduler` 发出（Pi 不知道四阶段语义）；内层 `turn`/`tool`/`thinking`/`output` 由 `PiAgentRunner.eventBridge` 转发，二者靠 `taskId` 关联。
- **权威值覆盖**：`thinking_delta` / `text_delta` / `toolcall_delta` 仅用于实时显示；`thinking_end.content` / `text_end.content` / `toolcall_end.toolCall` / `message_end.message` 必须覆盖增量拼接结果（附录 C）。`blockId = taskId + ":" + contentIndex`。
- **结束判定只认 `agent_settled`**（不认 `agent_end`，避免自动重试期间误判）；`lifecycle` 事件让 WebUI 能显示「压缩中 / 自动重试中」而不误标完成。
- **流式增量重建三原则**：① `contentIndex` 关联同一内容块；② `*_end` 的 `content` 是权威值；③ `message_end.message` 覆盖整个 partial 消息。
- **CLI**：只消费兼容子集（`status/step/done/info/warn`），渲染成原有彩色 `=== 状态 ===` / `>>> 步骤` / `✓ 完成` / `  ⚠ 警告`；新增事件在 CLI 中降级为 `info`，不破坏旧体验。
- **Web**：单条 `GET /api/stream/{id}` SSE 通道承载全部事件；`event:` 用 `SolveXEvent.type`，`id:` 用自增序号 → `Last-Event-ID` 断线续传；30s `ping`；`complete`/`error` 关流。`GET /api/events/{id}?since=N` 回放、`GET /api/stages/{id}` 拉全量 DAG 快照，刷新页面不丢「思考 + 阶段」。

### 4.7 工作区契约

完全沿用 §2.5 的目录与文件名，`@solvex/core/src/workspace/` 用 TypeScript 重写 `prepare_workspace / zip_workspace / list_sessions`，并修正两点：

1. **resume 不清理产物**：旧 `prepare_workspace()` 会 `shutil.rmtree(OUTPUT_DIRS)`，Web 端重跑会丢已完成模型（E2）。新实现：`prepareWorkspace({ mode: "create" | "resume" })`，resume 模式只读不删。
2. **上传解析统一**：CLI `--data` 与 Web `files[]` 走同一个 `ingestData()`（支持单文件 / 目录 / zip 自动解压），修掉 §2.6 的 multipart / JSON 不一致 bug。

---

## 5. 资产迁移映射

### 5.1 提示词迁移（★ 最高优先级）

**策略：`.py` 字符串常量 → `.md` 原文 + TS 模板渲染函数，逐字搬运，只做三类机械替换。**

| 规则 | 说明 |
| --- | --- |
| R-1 占位符 | Python `.format()` / f-string 变量 → 显式 `renderXxx(vars)` 函数，变量名保持不变（`{model_name}`、`{problem}`、`{model_plan}`、`{results}`、`{review_path}`、`{output_dir}`）；禁止引入模板引擎魔法 |
| R-2 工具名 | 提示词正文列举的工具名（`str_replace_editor`、`python_execute`、`terminate`、`arxiv_search`、`webSearchPrime`、`webReader`）→ 按 §4.5 映射到新白名单；**`terminate` 相关句子整体删除**（Pi 无此工具），并在 `programming/writing` 提示词末尾补一句「完成全部产物后直接给出结论，无需调用结束工具」 |
| R-3 "每次只调一个工具" | 旧提示词强制 `make exactly ONE tool call and wait` —— **保留**（对数学建模这种需逐步验证的场景有效），但改为软约束写入 `RESPONSE FORMAT`，不再依赖自研 loop 强制 |

**逐文件映射表**：

| 源 | 目标 | 备注 |
| --- | --- | --- |
| `modeling.py::SYSTEM_PROMPT` | `prompts/modeling.system.md` | 87 行，原样；含 `## Model N:` 强制分节格式（编排依赖） |
| `modeling.py::NEXT_STEP_PROMPT` | `prompts/modeling.next.md` | 原样 |
| `modeling.py::REVIEW_PROMPT` | `prompts/review.md` | 保留 `{...}` 占位符与 `VERIFICATION_RESULT` 双标记 |
| `programming.py::SYSTEM_PROMPT` | `prompts/programming.system.md` | 含 6 小节 `results_summary` schema、图片规范、`<think/>` 相关约束 |
| `programming.py::NEXT_STEP_PROMPT` | `prompts/programming.next.md` | `{output_dir}` 占位符 |
| `writing.py::SYSTEM_PROMPT` | `prompts/writing.system.md` | 含 7 条 CRITICAL RULES、LaTeX 结构、20–30 页目标 |
| `writing.py::NEXT_STEP_PROMPT` | `prompts/writing.next.md` | 原样 |
| `visualization.py::*` | `prompts/visualization.*.md` | 保留为可选 stage / skill |
| `solvex_flow.py` 内联 5 段 | `prompts/inline/{plan,implement,revision,fix,paper}.ts` | **见附录 A**，最易漏 |
| 其余 6 个 prompt 文件 | `docs/legacy-prompts/` 归档 | 不加载、不删除，保留审计线索 |

**提示词与 Pi 资源体系的关系（重要）**：

- **主链路**：不走 Skills / Prompt Templates，而是 `PiAgentRunner` 用 `DefaultResourceLoader.systemPromptOverride` 直接注入——因为四阶段是**程序驱动**的，需要确定性，不能让模型自己决定何时加载哪个 skill。
- **不做 `pi-package/`**（D6 已确认）：提示词只保留 `packages/core/src/prompts/*.md` 一份真源；如需交互式调试单个阶段，用 `solvex inspect <id>` 回看会话，不再维护第二份资产，也不做 `pi install` 分发。

### 5.2 编排逻辑映射

| 旧（Python） | 新（TypeScript） | 变化 |
| --- | --- | --- |
| `SolveXFlow.execute()` | `flow/SolveXFlow.ts::run()` | 同一四阶段顺序 |
| `_parse_models()` 正则 `## (Model \d+)` | `contracts/masterPlan.ts::parseModels()` | 保留正则兼容 + 增加 zod/TypeBox 校验；解析失败降级为 `["Model 1"]` 的行为保留 |
| `_extract_model_section()` | `contracts/masterPlan.ts::sectionFor()` | 保留 |
| `_validate_model_output()` | `gates/validateModelOutput.ts` | **升级**：返回结构化 `Issue[]`（code/severity/evidence），可配置阈值；保留原有 5 类检查（摘要存在/体积/`<think/>`/概率和/高概率占比/无图） |
| `VERIFICATION_RESULT` 字符串匹配 | `gates/parseVerdict.ts` | **双轨**：优先读结构化 `handoff.json`，回退正则匹配旧标记（保证旧 session 兼容） |
| master_plan 快照/还原 | 评审会话只读工具白名单 | 意图保留，实现升级（§4.4） |
| `results_summary.md` 自动兜底 | `gates/ensureSummary.ts` | 保留兜底但输出**结构化占位**（不塞原始工具输出），并打 `warn` 事件；解决 B2/E4 |
| `all_results_summary.md` 拼接 | `flow/stages.ts::aggregate()` | 纯函数，单测覆盖 |
| `_emit(queue, ...)` | `events/EventBus` | 事件类型兼容 + 结构化字段 |
| `resume_from` / `skip_to_writing` | `flow/resume.ts` | 行为对齐；自动探测逻辑（找首个缺 `results_summary.md` 的 model_N）保留 |
| `asyncio.wait_for` | `AbortSignal` + `session.abort()` | 超时可真正中止模型调用 |
| `FlowFactory` / `FlowType` | 删除 | 只剩一种 flow；用配置对象代替工厂 |
| `PlanningFlow` / `PlanningTool` | 删除 | 非主链路，归档到 `docs/legacy/` |

### 5.3 CLI 参数映射

| 旧 | 新 | 备注 |
| --- | --- | --- |
| `python run_flow.py -p FILE -d DIR` | `solvex run --problem FILE --data DIR` | 完全兼容 |
| `--resume ID --from-model N` | 同名 | 新增 `--session-dir` 覆盖 `~/.solvex/sessions` |
| `--skip-to-writing / -w` | 同名 | 行为不变 |
| — | **新增** `--concurrency N` | 并行上限（默认 3；`=1` 等价旧版串行），D2 |
| — | **新增** `--strict` | Critical 问题阻断进入 P4（D4 默认关闭） |
| 无参交互式输入 | `solvex run` 无参 → 交互式 | 保留 |
| `python api.py` → `:8000` | `solvex serve --port 8000` | 同一进程内嵌 core，不再需要 uvicorn |
| — | **新增** `solvex inspect <id>` | 用 Pi 的 `sessionManager` / `importFromJsonl` 回看某阶段会话（旧版无此能力） |
| — | **新增** `solvex validate <id>` | 单独重跑质量门，不改产物 |

### 5.4 Web API 映射

旧 4 个端点全部保留兼容，新增端点分三组（完整清单与负载见 **§10.8**）：

| 旧端点 | 新端点 | 变化 |
| --- | --- | --- |
| `POST /api/run` (Form/File) | 同名，统一 **multipart** | 修前端 `Content-Type` bug；返回 `{session_id}`；body 可带 `concurrency` / `strict` / `byPhase` |
| `GET /api/stream/{id}` | 同名 SSE | 事件结构按 §4.6 扩展；`ping` 心跳、`event:`/`id:` 与 `Last-Event-ID` 续传 |
| `GET /api/download/{id}` | 同名 ZIP | 不变 |
| `GET /api/sessions` | 同名 | 不变 |
| `GET /`, `/static/*` | 同名 | **前端整体重写为 WebUI 2.0**（不再复用旧三件套），见 §10 |
| — | `GET /api/artifacts/{id}` | 真实产物树（旧版 `showResults()` 是硬编码假列表） |
| — | `POST /api/abort/{id}` | 中止所有在跑并行任务 |
| — | `GET /api/events/{id}?since=N` | 历史事件回放（思考 / 输出 / 工具 / 用量） |
| — | `GET /api/stages/{id}` | 阶段 DAG 全量快照，刷新页面不丢进度 |
| — | `GET /api/models` | 可用模型列表 + 当前配置（**脱敏**） |
| — | `PUT /api/models/config` | 默认模型 / 按阶段分档 / scopedModels / thinkingLevel |
| — | `POST /api/models/refresh` | 刷新 catalog、重载 `models.json` |
| — | `POST /api/models/api-key` | 运行时注入凭据（只进内存） |
| — | `PUT /api/models/endpoints` | 增改自定义 OpenAI 兼容端点 |

### 5.5 明确丢弃清单

`app/agent/*`（全部）、`app/llm.py`、`app/bedrock.py`、`app/config.py`、`app/schema.py`、`app/service/compact.py`、`app/tool/*`（除 §4.5 保留项）、`app/mcp/*`、`app/sandbox/*`、`app/daytona/*`、`config/config.example*.toml`、`main.py`、`setup.py`、`requirements.txt`、`Dockerfile`、`app/prompt/{manus,mcp,planning,swe,toolcall,browser}.py`（归档而非删除）、`docs/superpowers/plans/*`（转为验收基线后归档）。

---

## 6. 关键设计决策（ADR 摘要）

| ID | 决策 | 理由 | 代价 |
| --- | --- | --- | --- |
| **ADR-01** | 用 SDK 内嵌，不 spawn `pi` 子进程 / 不采用 RPC | 同进程多 session、事件订阅、`abort()` 最直接；WebUI 与 CLI 共用 core | Node 进程承载模型长连接，需做好超时与取消 |
| **ADR-02** | `@solvex/core` 零 Pi 依赖，通过 `AgentRunner` 端口倒置 | 编排模式是本产品最核心资产；与 SDK 版本解耦，可纯 TDD | 多一层接口抽象 |
| **ADR-03** | 阶段间判定升级为**结构化 handoff + 旧标记兼容双轨** | 修 B2/C1/D4/E3/E4：靠自然语言找 `VERIFICATION_RESULT` 太脆弱 | 需在提示词里追加「同时写 `handoff.json`」的轻量指令（属于增强，不改变原有编排模式） |
| **ADR-04** | 每阶段独立 `AgentSession`，默认 `SessionManager.inMemory()` | 隔离上下文，消除 F2（压缩后质量下降）；一阶段失败不污染其他阶段 | 失去「跨阶段对话记忆」——但旧版本来也是每次 `memory = Memory()` 重置，行为一致 |
| **ADR-05** | 评审阶段使用只读工具白名单 | 从根上消除 A2/F3（评审覆写 master_plan），替代快照还原补丁 | 评审不能自己跑验证代码（改为读 `results_summary.md` + 质量门数据，与旧 REVIEW_PROMPT 一致） |
| **ADR-06** | 文件系统交接契约原样保留 | 可复现、可人工审阅是产品核心设计原则；旧 session 产物可继续用 | 需要严格的路径与 schema 校验 |
| **ADR-07** | 提示词以 `.md` 为**单一真源**；不做 Pi package（D6） | 避免两套资产漂移；一份文件同时供 SDK 注入与快照测试 | 失去交互式 `pi /solvex-*` 调试命令，改用 `solvex inspect <id>` |
| **ADR-08** | 工具按角色白名单收紧；`python_execute` 保留为自定义工具 | 旧提示词强依赖其语义；同时获得最小权限 | 需维护一个 TS 扩展 |
| **ADR-09** | 结束判定只认 `agent_settled` | `agent_end` 之后可能还有自动重试/压缩重试，误判会导致阶段提前结束 | 需正确订阅与超时兜底 |
| **ADR-10** | 不做云端/鉴权；WebUI 默认只监听 `127.0.0.1` | Pi 非安全沙箱，官方明确提示 | 远程访问需用户自行加反向代理/容器 |
| **ADR-11** | 无依赖即并行：core 内轻量 DAG + 屏障 + 并发上限，不引入外部编排引擎 | D2 已确认；缩短 N 模型总耗时，编排语义不变，`concurrency=1` 可回退串行 | 需处理写冲突、失败隔离、取消传播、resume 语义重定义 |
| **ADR-12** | Pi 原生 `thinking_*` 事件全量桥接到 SSE，前端按 `contentIndex` 重建、`*_end` 覆盖 | WebUI 必须显示思考过程；增量只用于实时显示，权威值在结束事件 | 事件量增大，需节流与体积上限（R12） |
| **ADR-13** | 模型 / 凭据配置全部留在后端，前端只见脱敏描述；`ModelRuntime` 单例 | 类 Pi 的模型配置体验 + 凭据不出后端（R13） | WebUI 不做 OAuth 浏览器回调，凭据靠 env / 运行时注入 / `models.json` |
| **ADR-14** | 阶段视图双层：外层 `stage` 由 core 发（权威），内层 turn/tool/thinking 由 `eventBridge` 转发，靠 `taskId` 关联 | Pi 不知道 SolveX 四阶段语义；两者结合才既能看「跑到哪」又能看「在想什么」 | EventBus 需维护 `taskId → 会话` 映射 |

---

## 7. 风险登记册

| ID | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | **Pi 版本漂移**：包名从 `@mariozechner/*` → `@earendil-works/*`；2026-10 移除实验性 server/client 包；SDK 导出可能变化 | 高 | `package.json` 锁定精确版本；`packages/pi-runtime` 是唯一 import 点；CI 加 `npm run typecheck`；升级前跑契约测试 |
| R2 | **Node 版本不足**：要求 ≥22.19，当前 22.13.1 | 高 | 阶段 0 先升级；`engines` 字段 + `.nvmrc` 固定 |
| R3 | **`max_steps` 无直接对应** | 中 | `turn_end` 计数 + `abort()` 预算；`timeoutMs` 双保险；保留旧默认 25/30/40 |
| R4 | **提示词工具名失配**：旧提示词写死 `str_replace_editor` / `terminate`，Pi 无这些工具 | 中 | 按 R-2 机械替换并做「提示词 → 工具白名单」一致性测试（提示词中出现的每个工具名必须在白名单里，反之亦然） |
| R5 | **安全**：Pi 工具以宿主进程权限运行，WebUI 可执行 `bash`/`python` | 高 | 默认绑定 `127.0.0.1`；`cwd` 限定在 session workspace；扩展 `tool_call` 拦截路径逃逸；生产部署用容器；文档显著警示 |
| R6 | **长文写作超时/截断**（旧 F1：80K tokens 单次响应） | 中 | 保留「分多次 edit 写、最后写摘要」提示词规则；Pi 内置 compaction + 自动重试；按阶段设 `timeoutMs` |
| R7 | **成本失控**：多模型 × **并行** × 多轮修订 × 长论文 | 中 | `RunRequest.maxTurns` / 全局 token-cost 预算；`usage` 按任务与全局两级汇总到 `RunSummary`；WebUI 顶部条实时显示，超预算停止派发新任务 |
| R8 | **旧 session 数据不兼容**（resume 场景） | 中 | 双轨解析（结构化 handoff + 旧标记）；`migrate-session` 命令把旧目录补齐 `handoff.json`；回归夹具用旧 session 产物 |
| R9 | **`03_figures/` 文档与代码不一致** | 低 | 以代码为准；新 README 明确图片落在 `02_programming/model_n/figures/` |
| R10 | 模型供应商切换导致行为差异（旧版用 DeepSeek Reasoner） | 中 | `models.json` 固定默认模型；golden 回归测试固定 provider/model；允许按阶段分档 / `scopedModels` 覆盖 |
| R11 | **并行写冲突**：多个 LLM 会话同时写共享文件（`all_results_summary.md` / `master_plan.md`） | 高 | 共享文件只由 P3 纯代码聚合生成；`master_plan.md` 全程只读；每个任务按 `taskId` 限定 `writablePrefixes`；扩展 `tool_call` 拦截越界写入；`concurrency=1` 对照测试 |
| R12 | **thinking 事件体量 / 敏感内容**：长思考流式洪泛、正文含路径或数据片段、`redacted` 块 | 中 | 前端节流 60–100ms；单块 ≤64KB 截断并标记；`persistThinking: false` 默认不落盘；回放/导出做 `<think/>` 残留清洗；**思考视图与产物隔离**（Q-B2 仍由 `ensureSummary()` 保证） |
| R13 | **WebUI 凭据泄露**：API Key 经 `/api/models`、日志或 `events.jsonl` 外泄 | 高 | 一律不回传明文，只回 `masked`；`models.json` 用 `$ENV` 插值；运行时 key 只进内存；默认 `127.0.0.1`（ADR-10） |
| R14 | **并行放大失败面**：单任务失败/限流在 N 路并发下被放大，屏障处集体超时 | 中 | 并发上限默认 3 且可调；失败隔离（不取消他任务）；Pi 内建重试/compaction 承接单任务；屏障超时可配置；提供「重试失败项」 |

---

## 8. 验收标准

### 8.1 功能验收

| # | 用例 | 期望 |
| --- | --- | --- |
| F-1 | `solvex run --problem tests/simple/linear_programming/problem.md` | 完整跑通 P1→P4，生成 master_plan / model_N / all_results_summary / main.tex |
| F-2 | `--data` 指向 CSV/ZIP | 数据被 ingest 到 `data/`，且 P1 提示词中的 `DATA FILES` 清单正确 |
| F-3 | `--resume ID --from-model 2` | 不删除已有 model_1 产物；从 model_2 继续 |
| F-4 | `--skip-to-writing` | 只生成/更新 `04_paper/main.tex` |
| F-5 | `solvex serve` + WebUI 提交（含文件上传） | SSE 实时进度、完成后下载 ZIP、`/api/artifacts` 返回真实文件树 |
| F-6 | 运行中 `POST /api/abort/{id}` | 当前阶段 session 被 `abort()`，状态标记 `aborted`，产物不损坏 |
| F-7 | 刷新 Web 页面 | `/api/events/{id}` + `/api/stages/{id}` 回放，「思考过程 + 阶段进度」都不丢失 |
| F-8 | WebUI 模型配置中心 | `GET /api/models` 只列凭据可用模型；可切换默认模型、thinking 档位、按阶段分档；自定义兼容端点保存并 refresh 后出现在选择器；**任何响应不含明文 API Key** |
| F-9 | WebUI 思考过程显示 | 选择支持 reasoning 的模型后，思考块流式出现、默认折叠可展开；`thinking_end` 权威值覆盖增量；`redacted` 块优雅降级 |
| F-10 | WebUI 运行阶段显示 | 右栏 DAG 时间线显示 P1→P2(并行 N)→P3→P4；并行任务状态独立刷新；展开任务卡片可见 turn / 工具 / 思考 / 输出；`agent_settled` 前不误标完成 |
| F-11 | 并行执行 | `--concurrency 3` 下 N 个模型并行；`concurrency=1` 与串行产物逐字节一致；单模型失败不影响其他任务 |
| F-12 | 并行写安全 | 断言无任何 LLM 会话写 `all_results_summary.md` / `master_plan.md`；越界写入被 `tool_call` 拦截；`all_results_summary.md` 只由 P3 生成 |
| F-13 | 用量与成本 | 顶部条实时显示 token / ¥；`RunSummary.usageByTask` 与全局一致；`reasoning` token 不重复计入 |

### 8.2 质量门验收（对应旧 23 问题）

| # | 旧问题 | 新架构的验收断言 |
| --- | --- | --- |
| Q-A2 / F3 | master_plan 被评审覆写 | 评审会话工具白名单不含 `write/edit`；单测断言评审前后 master_plan 字节一致 |
| Q-B2 / E4 | 兜底摘要泄漏 `<think/>` 与原始工具输出 | `ensureSummary()` 产物不含 `<think/>`、不含 `` ` `` 包裹的原始 JSON；带 `⚠` 标记 |
| Q-B4 / C2 | 概率未校准未被发现 | `validateModelOutput()` 返回 `PROBABILITY_SUM_OUT_OF_RANGE` / `UNCALIBRATED_PROBABILITIES` 结构化 Issue，且 `warn` 事件可见 |
| Q-B5 | results_summary 格式不统一 | `ModelResult` schema 校验通过率 100%；缺小节即触发定向修复 |
| Q-C1 | 评审文件没生成 | 评审阶段结束断言 `*_review.md` 存在且含合法 `Verdict` |
| Q-D1 / D4 | 编造数字与指标 | `writing` 提示词快照含「USE ONLY the results provided」；回归测试比对论文中数值与 `all_results_summary.md` 的一致性（至少抽样） |
| Q-D3 | 摘要与结论矛盾 | 提示词快照含「WRITE ORDER: body FIRST, abstract LAST」 |
| Q-E1 | 1h 超时太紧 | 每阶段独立 `timeoutMs` + resume；不再有全局 3600s 硬杀 |
| Q-E2 | resume 删除已完成产物 | `prepareWorkspace({mode:"resume"})` 单测断言不调用删除 |
| Q-E3 | 阶段间无验证门 | P2→P3 之间强制 `validateModelOutput()`；Critical Issue 阻断进入 P4（可配置 `strict` 开关） |
| Q-F1 / F2 | 超长响应 / 压缩掉质量 | 由 Pi 内置 compaction + 阶段隔离会话承接；回归用同一 2025 C 夹具跑通 |
| Q-Web | multipart/JSON 不一致 | Web 提交带文件上传的集成测试通过 |

### 8.3 非功能验收

- 仓库中 `grep -r "openai\|anthropic\|requests" packages/core` 无结果（core 零模型 SDK 依赖）。
- `npm run typecheck && npm test` 全绿；core 单测覆盖率 ≥ 85%（编排状态机 100% 分支）。
- 提示词快照测试：所有 `.md` 与 `docs/legacy-prompts/` 的搬运结果逐字比对通过（仅允许 R-1/R-2/R-3 白名单差异）。
- 端到端：2025 MCM Problem C 夹具跑通，产物目录结构与旧 session 兼容。
- 并行：`flow/scheduler.ts` 单测覆盖屏障、并发上限、失败隔离、取消传播，分支覆盖率 100%。
- WebUI：`test/web/store.test.ts` 用构造的 `SolveXEvent` 序列断言 `thinking` / `stage` / `usage` 的 reducer 纯函数正确（不依赖 DOM）。
- 事件契约：`thinking_delta` 拼接结果必须等于 `thinking_end.content`；`message_end` 覆盖 partial 消息；`agent_end` 不产生 `done`（附录 C）。
- 安全：`grep -r "sk-\|apiKey" apps/web/public` 无明文；`/api/models` 响应体快照测试断言所有密钥字段均为 `masked`。

---

## 9. 决策记录（v1.1 已确认）

| ID | 决策 | 状态 | 落地位置 |
| --- | --- | --- | --- |
| **D1** | 只用 **Pi 官方 TS SDK `@earendil-works/pi-coding-agent`**；不用 `pi-agents` / 第三方 orchestrator / RPC 子进程 | ✅ 已确认 | §3.3、§3.5、§4、计划阶段 3 |
| **D2** | **无依赖即并行**：P2 的 N 个实现、N 个评审并行；有依赖处设屏障；并发上限可配，`=1` 可回退串行 | ✅ 已确认 | §4.4.1、§10.5.2、计划 T2.9 |
| **D3** | 结构化 `handoff.json` + 旧文本标记**双轨** | ⚠️ 按推荐默认执行（下方详解） | ADR-03、T2.4、T6.12 |
| **D4** | Critical 默认**告警不阻断** + `--strict` / Web「严格模式」开关 | ⚠️ 按推荐默认执行（下方详解） | §8.2 Q-E3、T2.8d、T6.10 |
| **D5** | 默认模型不硬编码，由 `models.json` + env 决定；**按阶段分档**；WebUI 可随时切换 | ⚠️ 按推荐默认执行（下方详解） | §3.6、§10.3、T3.1/T3.6 |
| **D6** | **不做** `pi-package/` | ✅ 已确认 | §1.3、§4.2、ADR-07、计划阶段 8 |

> D3 / D4 / D5 用户要求「解释清楚一点」，以下逐项展开：**背景 → 有哪些选项 → 各自代价 → 推荐哪个及为什么 → 会影响哪些文件 → 想改的话怎么说**。三者的推荐默认已写进实施计划，不会再阻塞开工；若你要改，直接指出 ID 即可。

### 9.1 D3 详解：要不要引入结构化 `handoff.json`

**背景（为什么会有这个问题）**：旧版所有阶段间判定都靠**在自然语言输出里找固定字符串**——`VERIFICATION_RESULT: SATISFIED / NEEDS_REVISION`（决定是否重新实现）、`## Model N:`（切分 Master Plan）、`## Fix Instructions:`（定向修复）。仓库自带的 23 问题清单里，B2（摘要泄漏 `<think/>`）、E4（兜底摘要污染）、C1（评审文件没生成）、D4（编造指标）都跟这条脆弱链路有关：模型把标记写进摘要、标记丢失、标记被思考标签污染，flow 就会误判或静默放行。

**三个选项**：

| 选项 | 做法 | 优点 | 代价 |
| --- | --- | --- | --- |
| A. 100% 纯文本标记 | 提示词零改动，新架构照旧正则匹配 | 最"原教旨"地保留编排模式；旧 session 100% 兼容 | 误判问题原样带进新架构；质量门拿不到结构化数据；WebUI 阶段卡片显示不出 verdict / issues，只能显示「跑完 / 没跑完」 |
| B. 纯结构化 handoff | 只认 `handoff.json`，删除所有文本标记 | 最干净、最强类型 | 旧 session 全部无法 resume；要改写 5 段内联提示词，违反「提示词逐字搬运」硬约束 |
| **C. 双轨（推荐）** | 编排层**优先**读 `02_programming/model_n/handoff.json`（TypeBox 校验 `{status, issues[], fixInstructions, summaryPath}`）；读不到或校验失败**回退**正则匹配旧标记 | 老 session 可续跑，新运行有强类型数据；WebUI 能直接显示 verdict 与 issues；修 B2/C1/E4 | 提示词需追加**一句**指令；多一个契约文件与一条解析分支 |

**推荐 C 的具体落地**：只在 `programming.system.md` 末尾追加一句「除正文中的 `VERIFICATION_RESULT` 标记外，同时把同一结论写入 `handoff.json`」——这是**增强，不是改写语义**，属于 §5.1 快照白名单里唯一允许的新增。`gates/parseVerdict.ts` 做双轨；`solvex migrate-session <id>` 可为旧目录补生成 handoff。两者冲突时以 `handoff.json` 为准并记 `warn`。

**影响面**：`contracts/handoff.ts`、`gates/parseVerdict.ts`、提示词快照白名单、`RunSummary.issues`、WebUI 阶段卡片、T6.12 回归夹具。**想改成 A 或 B**：说一句「D3 改 A」/「D3 改 B」，改这 3 处即可，其余架构不动。

### 9.2 D4 详解：质量门发现 Critical 时停不停

**背景**：`validateModelOutput()` 会给每个模型产出 `Issue[]`，分 `critical`（无代码 / 无摘要 / 概率和 >50 / 概率未校准 / 无图）与 `warn`。旧版 E3「阶段间无验证门」是 23 问题的根因之一。这里要决定的**不是「要不要验证门」——两种模式都有验证门**，而是「**发现 Critical 后，是停下还是继续跑完**」。

| 选项 | 行为 | 优点 | 代价 |
| --- | --- | --- | --- |
| **A. 默认告警不阻断（推荐）** | Critical 发 `warn` 事件、记入 `RunSummary.issues`，流程继续到 P4 | 数学建模竞赛场景里「先出完整论文再回头修」比「卡在第 3 个模型」更符合实际；与旧版「一次跑完」行为一致；WebUI 能标红但不打断长跑；并行下不会因单个模型拖垮整批 | 可能带坏数据进论文——由 writing 提示词的 `USE ONLY the results provided` + 数值抽样一致性测试（Q-D1/D4）兜底 |
| B. 默认阻断 | Critical 直接抛错，不进 P4，要求修复后重跑 | 最"正确"，E3 修得最彻底 | 一次多模型并行长跑可能因单个模型的图片规格问题整体失败，体验差；与既有产品行为不一致 |

**推荐 A + 开关**：默认 A；同时实现 `--strict`（CLI）与 WebUI「严格模式」开关（默认关），开关打开时等价于 B。两者成本只差一个 `if`，所以**不是二选一，而是「哪个当默认」**。WebUI 在阶段卡片上把 Critical 标红，并提供「以严格模式重跑」按钮。

**影响面**：`SolveXFlow` 的 P2→P3 门、`RunSummary`、CLI `--strict`、WebUI 严格模式开关、T2.8d / T6.10 测试。**想改成 B 当默认**：说「D4 默认阻断」，把默认值翻过来即可。

### 9.3 D5 详解：默认模型、按阶段分档、thinking 档位

**背景**：旧版 `config/config.example*.toml` 有 7–8 份模板，README 用 DeepSeek Reasoner（单次 80K tokens，正是 F1 的根因），另有 Claude 模板。Pi 改用 `models.json` + `auth.json` + 环境变量，支持 15+ provider、OAuth、自定义兼容端点。这里其实藏着**三个子问题**：

1. **默认用哪个模型？** —— 不硬编码。由 `models.json` 的 `defaultProvider`/`defaultModel` 或环境变量决定；**首次启动若无可用凭据，WebUI 模型配置中心直接引导配置**（§10.3），CLI 给出清晰错误而非静默失败。golden 回归测试固定 provider/model 以隔离变量（R10）。
2. **不同阶段用不同模型吗？** —— 用。`RunRequest` 增加按阶段分档（P1 建模 / P2 实现 / P2 评审 / P4 写作），映射到 Pi 的 `createAgentSession({ model, scopedModels })`。典型建议：P1 与 P2-REVIEW 用强推理模型 + `thinkingLevel: "high"`，P2-IMPL 用性价比模型 + `"medium"`，P4 用长上下文模型。这**只是默认建议**，WebUI 可逐阶段改，不锁死。
3. **thinking 档位怎么定？** —— 7 档 `off / minimal / low / medium / high / xhigh / max`，Pi 会按模型能力裁剪，WebUI 只列该模型支持的档位；不支持 reasoning 的模型自动降为 `off`。注意 `Usage.reasoning` **已包含在 `output`**，汇总成本时不要重复累加。

**推荐落地**：`packages/pi-runtime/models.json` 只放 provider / 端点定义（密钥用 `$ENV` 插值，不放明文）；`settings.json` 的 `defaultThinkingLevel` 默认 `medium`；`byPhase` 配置放我们自己的 `~/.solvex/config.json`，由 WebUI 模型配置中心读写，落到每个 `RunRequest`（§3.6、§10.3）。

**影响面**：T3.1 / 新增 T3.6、§10.3、R10、WebUI 顶部状态条。**如果你已有偏好的固定模型**（例如继续用某个 DeepSeek 兼容端点），把 `provider/id` 告诉我，我把它写进 `models.json` 默认值与回归测试的 golden 常量；否则就按「有啥凭据用啥，WebUI 里随时可切」。

---

## 10. WebUI 2.0 设计规格（本次确认的重点升级）

### 10.0 为什么整体重写，而不是沿用旧 UI

旧 `static/` 三件套约 11 KB：侧栏历史 + 输入框 + 进度流 + **硬编码假结果卡片**，且 `startRun()` 的 multipart bug 与 `showResults()` 假列表都是已知缺陷。它只把「进度」当日志打印，**完全没有「模型 / 思考 / 阶段」三个维度**。用户已明确要求 WebUI 大幅升级并对齐 Pi 的交互体验，因此前端整体重写（URL 与端点保持兼容），不是打补丁。

### 10.1 对标映射：Pi TUI → SolveX WebUI 2.0

| Pi 交互 | 用户感受 | WebUI 2.0 对应 | 数据来源 |
| --- | --- | --- | --- |
| `/model` 搜索选择，`Ctrl+S` 存默认 | 随手切模型 | 顶部「模型配置中心」抽屉：可搜索、按 provider 分组、显示能力/上下文/价格，一键设为默认 | `ModelRuntime.getAvailable()` |
| `/thinking` 选档，`Ctrl+S` 存启动档 | 控制思考强度 | 每角色/每阶段 thinking 档位（7 档），按模型能力过滤 | `defaultThinkingLevel` / `modelThinkingLevels` |
| `/scoped-models` + `Ctrl+P` 循环 | 预设模型集合 | 「按阶段分档」+ 循环模型集 | `createAgentSession({ scopedModels })` |
| `/login` / `auth.json` / env / `models.json` 自定义端点 | 统一凭据管理 | 凭据面板：环境变量只读（遮蔽）、运行时注入 Key、自定义 OpenAI 兼容端点、凭据优先级说明 | `ModelRuntime.create({authPath, modelsPath})` / `setRuntimeApiKey()` |
| TUI 中灰显、可折叠的 thinking block | 看得到模型在想什么 | 「思考过程」视图：按 `contentIndex` 流式追加、默认折叠、可展开/隐藏、`redacted` 优雅降级 | `thinking_start/_delta/_end` |
| 消息流里的工具块 + turn 分隔 + 底部状态栏（模型/thinking/token/cost） | 全程可观测 | 「运行阶段」时间线 + 工具卡片 + 顶部实时用量条 | `turn_*` / `tool_execution_*` / `usage` |
| `agent_settled` 才表示真正结束 | 进度不误判 | 阶段状态由编排层 `stage` 事件驱动，Pi 事件只作会话内细节 | `EventBus` |

### 10.2 信息架构与布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ SolveX ● 运行中 │ 模型 anthropic/claude-…  Thinking: high             │
│ 0423-b8a2       │ 输入 12.4K / 输出 8.1K / ¥3.42   [中止] [模型⚙]     │
├───────────┬────────────────────────────────────────┬─────────────────┤
│ 左：会话  │ 中：主工作区（标签页）                  │ 右：阶段时间线  │
│ 历史列表  │ [阶段视图] [思考过程] [产物] [日志]     │ P1 ● 完成       │
│ + 新建    │                                        │ P2 ◐ 3/5 并行   │
│           │ 阶段视图：DAG 卡片，点开某任务 →        │  ├ model_1 ✓    │
│           │   该 session 的 turn 流 / 思考 /        │  ├ model_2 ◐思考 │
│           │   工具调用 / 文本输出                   │  ├ model_3 ◐跑码 │
│           │ 思考过程：当前与历史 thinking block     │  ├ model_4 ○排队 │
│           │ 产物：真实文件树 + 预览 + 下载 ZIP      │  └ model_5 ○排队 │
│           │ 日志：原始 SolveXEvent（开发者用）      │ P3 ○ 等待屏障   │
│           │                                        │ P4 ○ 等待       │
├───────────┴────────────────────────────────────────┴─────────────────┤
│ 底部：问题输入 + 数据拖拽上传 + 并行度滑块(1..N) + 严格模式 + [开始]  │
└──────────────────────────────────────────────────────────────────────┘
```

- **顶部条** = Pi 状态栏的 Web 等价：当前模型、thinking 档、token、¥ 成本实时刷新。
- **右栏** = 「运行阶段显示」主载体；并行子任务一目了然，屏障处显示 `3/5`。
- **中栏**把「思考过程」独立成标签页，同时内嵌在每张阶段卡片里；模型配置做成抽屉，不占主区。
- **底部**把 D2 的 `concurrency` 与 D4 的 `strict` 变成可见控件。

### 10.3 模型配置中心（Model Studio）

#### 10.3.1 数据模型

```ts
type ModelDescriptor = {
  provider: string; id: string; name?: string;
  reasoning: boolean;                 // 是否支持 thinking
  input: ("text"|"image")[];
  contextLimit?: number; maxOutput?: number;
  price?: { input: number; output: number };   // 每百万 token
  available: boolean;                 // 凭据是否就绪
  source: "builtin"|"models.json"|"extension";
};

type ModelConfig = {
  defaults: { provider?: string; model?: string; thinkingLevel: ThinkingLevel };
  byPhase: Partial<Record<"P1"|"P2_IMPL"|"P2_REVIEW"|"P3"|"P4",
                   { provider: string; model: string; thinkingLevel?: ThinkingLevel }>>;
  scopedModels: string[];
  thinkingLevels: ThinkingLevel[];    // 按当前模型裁剪后返回
  credentials: { provider: string;
                 source: "env"|"auth.json"|"runtime"|"models.json";
                 masked: string; status: "ok"|"missing" }[];
  endpoints: { id: string; baseUrl: string; api: string; models: string[] }[];
};
```

#### 10.3.2 交互细节（对齐 Pi 体验）

- 搜索框 + provider 分组 + 能力标签（reasoning / vision / 上下文 / 单价）；**只列出凭据可用的模型**（`getAvailable()`），未配置的置灰并给「去配置凭据」入口。
- 每个模型行：`设为默认`（≡ `Ctrl+S`）、`加入循环集`（≡ `/scoped-models`）、`分配到阶段`（P1/P2/P3/P4）。
- thinking 档位**按所选模型过滤**，不支持 reasoning 时自动降为 `off` 并给出提示。
- 自定义端点表单：`baseUrl` / `api` / `apiKey`（支持 `$ENV` 插值）/ `models[]`；保存后 `POST /api/models/refresh` 即刻出现在选择器（等价 Pi 的「打开 `/model` 会重载文件」）。
- 显著展示凭据优先级：runtime `--api-key` > `auth.json` > `models.json.apiKey` > 环境变量。
- **安全**：`apiKey` 一律不回传，只回 `masked: "sk-••••1234"`；`GET /api/models` 响应体不含任何明文密钥（R13 / ADR-13）。

#### 10.3.3 落到会话

`RunRequest` 增加 `model` / `thinkingLevel` / `scopedModels`（§4.3）；`PiAgentRunner` 持有**单例 `ModelRuntime`**（`ModelRuntime.create({authPath, modelsPath})`），避免每阶段重建 catalog；`createAgentSession({ model, thinkingLevel, scopedModels, modelRuntime })`。`byPhase` 未指定时回落 `defaults`；`thinkingLevel` 未指定时回落 `settings.json` 的 `defaultThinkingLevel`。

### 10.4 思考过程视图

#### 10.4.1 事件 → 渲染映射

| Pi 事件 | SSE `SolveXEvent` | 前端动作 |
| --- | --- | --- |
| `thinking_start` | `{type:"thinking", state:"start", blockId, contentIndex}` | 新建折叠块，标记「思考中」 |
| `thinking_delta` | `{type:"thinking", state:"delta", delta}` | 追加正文（节流 60–100ms） |
| `thinking_end` | `{type:"thinking", state:"end", content}` | **用权威 content 覆盖**增量拼接 |
| `text_delta` / `text_end` | `{type:"output", ...}` | 正文流 |
| `toolcall_*` | `{type:"tool", state:"delta"...}` | 参数流 |
| `thinking_level_changed` | `{type:"model", thinkingLevel}` | 顶部条同步 |
| `message_end` | `{type:"output", state:"final", message}` | 用权威消息整体替换该 turn 的临时内容 |

**重建三原则**（Pi 官方，必须实现，否则刷新/回放会重复或丢失）：① `contentIndex` 关联同一内容块；② `*_delta` 只用于实时显示，`*_end` 的 `content` 是权威值；③ `message_end.message` 覆盖整个 partial 消息。

#### 10.4.2 展示策略

- **默认折叠**，摘要行显示「思考 12.4s · 1,842 字 · 点击展开」；提供全局「隐藏思考」开关（映射 `hideThinkingBlock` 语义）。
- `redacted: true` 的块（有 `thinkingSignature` 但无可见文本）显示「该模型的思考内容不可见」，不报错。
- **脱敏与体积**：单块 ≤ 64 KB，超出截断并标记；`persistThinking: false` 时思考正文不落盘；回放/导出做 `<think/>` 残留清洗（R12）。
- **与产物严格隔离**：思考视图展示的是 Pi 原生 thinking block，与旧版 `results_summary.md` 里泄漏的 `<think/>` 是两回事；**绝不把 thinking 内容写进任何产物**，Q-B2 仍由 `ensureSummary()` 保证。
- 思考按 `taskId` 独立成流，并行时各卡片分栏不混淆；长思考自动滚动 + 「暂停滚动」按钮。

### 10.5 运行阶段视图

#### 10.5.1 双层模型（ADR-14）

- **外层（编排层，权威）**：`SolveXFlow` / `scheduler` 发 `stage` 事件，描述 P1 → P2(并行 N) → P3 → P4 的 DAG、屏障与状态。这是用户理解的「运行到哪一步」。
- **内层（Pi 会话，细节）**：任务卡片展开后显示该 session 的 `turn_start/turn_end`、`tool_execution_*`、`thinking_*`、`output`。

只用 Pi 事件不行（Pi 不知道四阶段语义，也不知道「3/5 个模型已完成」）；只用编排层事件又看不到工具与思考。二者靠 `taskId` 关联。

#### 10.5.2 并行 DAG（D2 已确认）

见 §4.4.1 的依赖图。WebUI 侧要点：右栏节点状态独立刷新；屏障节点显示 `completed/total`；单任务失败标红但不阻塞兄弟节点；`POST /api/abort/{id}` 一次取消所有在跑任务；失败项提供「重试」按钮（复用 resume 语义）。

#### 10.5.3 `stage` 事件负载

`StageNode` 定义见 §4.6。前端用扁平 `StageNode[]` + `dependsOn` 还原 DAG；`stage` 事件为增量 patch（`{op:"upsert"|"remove", node}`），`GET /api/stages/{id}` 返回全量快照供首屏与刷新。节点携带 `turns` / `toolCalls` / `usage` / `thinkingMs` / `verdict` / `issues`，让「阶段」不只是进度条，而是可诊断的面板。

#### 10.5.4 顶部实时用量条

`usage` 取 Pi `message_update.usage`（`input/output/cacheRead/cacheWrite/totalTokens/cost`；`reasoning` 已含在 `output` 不再重复计），按任务与全局两级汇总进 `RunSummary.usageByTask`。WebUI 顶部显示 token 与 ¥，超预算发 `warn`（R7 / R14）。

### 10.6 SSE 与刷新回放

- `GET /api/stream/{id}`：单通道承载全部 `SolveXEvent`；`event:` = `type`，`id:` = 自增序号，支持 `Last-Event-ID` 续传；30s `ping`；`complete`/`error` 关流。
- `GET /api/events/{id}?since=N` 历史事件回放；`GET /api/stages/{id}` 阶段 DAG 全量快照。**刷新页面先拉这两个，再接 SSE**，保证思考与阶段都不丢。
- `EventBus.history()` 落 `~/.solvex/sessions/{id}/events.jsonl`（含体积上限与轮转；`persistThinking: false` 时思考正文不落盘）。

### 10.7 前端技术选型与状态管理

- **默认无构建链**：原生 ES modules，直接 `apps/web/public/{index.html, app.js, styles.css}` + `modules/{store, stream, models, thinking, stages, artifacts}.js`；保持「CLI 工具 + 静态 UI」的轻量形态（如团队接受构建步骤可换 Preact + Vite，但不作为默认）。
- 单一 `SessionStore`：`{ config, stages: Map, tasks: Map<taskId, {thinkingBlocks, turns, tools, output}>, usage, events[] }`；SSE 事件经**纯函数** `reduce(event)` 更新，配 `test/web/store.test.ts` 做 RED→GREEN，不依赖 DOM。
- `thinking` / `output` 的增量缓冲以 `contentIndex` 为 key；`*_end` 与 `message_end` 覆盖；渲染函数纯函数化。

### 10.8 Web API 全量清单

| 组 | 端点 | 方法 | 说明 |
| --- | --- | --- | --- |
| 兼容 | `/api/run` | POST | multipart `text` + `files[]`；可带 `concurrency` / `strict` / `byPhase` → `{session_id}` |
| 兼容 | `/api/stream/{id}` | GET | SSE 全事件流，`Last-Event-ID` 续传，30s `ping` |
| 兼容 | `/api/download/{id}` | GET | workspace ZIP |
| 兼容 | `/api/sessions` | GET | 历史会话列表 |
| 产物 | `/api/artifacts/{id}` | GET | 真实产物树 |
| 产物 | `/api/events/{id}?since=N` | GET | 历史事件回放 |
| 运行 | `/api/stages/{id}` | GET | 阶段 DAG 全量快照 |
| 运行 | `/api/abort/{id}` | POST | 取消所有在跑任务 |
| 模型 | `/api/models` | GET | 可用模型 + 当前配置（脱敏） |
| 模型 | `/api/models/config` | PUT | 默认 / 分档 / scopedModels / thinkingLevel |
| 模型 | `/api/models/refresh` | POST | 刷新 catalog、重载 `models.json` |
| 模型 | `/api/models/api-key` | POST | 运行时注入凭据（只进内存） |
| 模型 | `/api/models/endpoints` | PUT | 自定义兼容端点 |
| 模型 | `/api/models/thinking-levels?model=` | GET | 该模型支持的档位 |

### 10.9 安全与隐私边界

- 只监听 `127.0.0.1`（ADR-10 / R5）；Pi 工具以宿主进程权限运行，官方明确非沙箱。
- API Key 不回传前端、不写日志、不进 `events.jsonl`；`models.json` 密钥用 `$ENV` 插值。
- thinking 正文默认只在内存与 SSE 流转（`persistThinking: false`），导出 ZIP 不含思考记录；单块体积上限与 `<think/>` 清洗（R12）。
- 工具 `bash` / `python_execute` 仍受 R5 路径拦截 + `cwd` 限制；并行时追加 `writablePrefixes` 前缀隔离（R11）。

### 10.10 验收口径

见 §8.1 的 **F-8 ~ F-13** 与 §8.3 的 WebUI / 并行 / 事件契约 / 安全四条非功能断言；实施计划阶段 5 拆为 5A（后端 API + SSE + 模型配置桥接）与 5B（前端组件 + store 单测）。

---

## 附录 A：内联提示词清单（最易漏的资产）

以下 5 段提示词不在 `app/prompt/`，而是硬编码在 `app/flow/solvex_flow.py`，迁移时必须一并搬走：

| # | 位置（行） | 变量 | 关键内容 |
| --- | --- | --- | --- |
| 1 | L181–188 | `modeling_prompt` | `PROBLEM:` + `DATA FILES` + 「write a multi-model Master Plan to {path}」+「Each model gets its own '## Model N: Name' section」 |
| 2 | L200–205 | `retry_prompt` | `URGENT: Write a multi-model Master Plan NOW...`（P1 失败重试话术） |
| 3 | L242–251 | `programming_prompt` | `PROBLEM` + `DATA FILES` + `=== YOUR TASK: Implement {model_name} ===` + `MODEL PLAN` 分节 + 三个输出路径（代码/`figures/`/`results_summary.md`） |
| 4 | L295–302 / L350–357 | `revision` / `fix_prompt` | `=== Re-implement {model_name} (REVISION) ===` + `PREVIOUS RESULTS`；`=== Fix ... (TARGETED REVISION) ===` + `## FIX INSTRUCTIONS` 片段 + 「Fix ONLY the issues above」 |
| 5 | L418–437 | `write_prompt` | `PROBLEM` + `MASTER PLAN` + `ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE)` + `AVAILABLE FIGURES (INSERT ALL OF THEM)` + LaTeX 图片相对路径规则 + 4 条 CRITICAL + **WRITE ORDER: body first, abstract last** |

另：`app/flow/planning.py::PLANNING_SYSTEM_PROMPT` 与 `_execute_step()` 里的 `step_prompt` 属于 `PlanningFlow`（非主链路），归档即可。

## 附录 B：Pi SDK API 速查

| 用途 | API |
| --- | --- |
| 创建会话 | `createAgentSession({ cwd, sessionManager, resourceLoader, model, thinkingLevel, scopedModels, modelRuntime, settingsManager, tools, noTools, excludeTools, customTools })` |
| 模型与凭据 | `ModelRuntime.create({authPath, modelsPath})`、`getAvailable()`、`getModel(provider,id)`、`setRuntimeApiKey(provider,key)` |
| 设置 | `SettingsManager.create(cwd)` / `.inMemory()`、`getGlobalSettings()`、`applyOverrides()`、`setDefaultThinkingLevel()`、`flush()`、`drainErrors()` |
| thinking 档位 | `off / minimal / low / medium / high / xhigh / max`（按模型能力裁剪；`Usage.reasoning` 已含在 `output`） |
| 配置字段 | `defaultProvider` / `defaultModel` / `defaultThinkingLevel` / `modelThinkingLevels` / `enabledModels` / `hideThinkingBlock` / `models.json.providers.*` |
| 会话管理 | `SessionManager.inMemory()` / 默认持久化；`AgentSessionRuntime.newSession()/switchSession()/fork()/importFromJsonl()` |
| 资源 | `new DefaultResourceLoader({ cwd, agentDir, systemPromptOverride, appendSystemPromptOverride, additionalExtensionPaths, extensionFactories })` + `.reload()`；`getAgentDir()` |
| 运行 | `session.prompt(text)`、`session.steer()`、`session.followUp()`、`session.abort()`、`session.waitForIdle()`、`session.getLastAssistantText()`、`session.dispose()`、`session.bindExtensions()` |
| 状态 | `session.messages` / `.model` / `.thinkingLevel` / `.systemPrompt`(只读) / `.getActiveToolNames()` |
| 事件 | `session.subscribe(fn)` → `message_update`(delta) / `message_end` / `tool_execution_*` / `agent_end` / **`agent_settled`** / `compaction_*` / `auto_retry_*` / `queue_update` / `entry_appended` |
| 扩展 | `pi.registerTool/registerCommand/registerShortcut/registerFlag/registerProvider/on/appendEntry`；`ctx.ui.*`；TypeBox `Type.Object()` 定义参数 |
| 内置扩展 | `createCodemodeExtension()`、`createToolSearchExtension()`、`createMcpExtension()`（SDK 会话默认不加载，需显式加入 `extensionFactories`） |
| 工具名 | `read` / `write` / `edit` / `bash` / `grep` / `find` / `ls` |
| CLI 模式 | `pi`（交互）/ `pi --print "q"` / `pi --mode json "q"` / `pi --mode rpc` / `RpcClient.promptAndWait()` |
| 资源目录 | `~/.pi/agent/{extensions,skills,prompts,agents}/`、项目 `.pi/...`（需 project trust）、`AGENTS.md`、`SYSTEM.md`、`models.json` |
| 打包 | `package.json` → `pi: { extensions, skills, prompts, themes, changelogPath }`；`pi install npm:... / git:... / ./local` |

## 附录 C：事件类型对照（旧 → Pi → SSE）

| 旧 `_emit` | Pi SDK 事件 | 新 SSE |
| --- | --- | --- |
| `status` | 阶段开始（编排层发） | `status` + `phase` |
| `step` | `tool_execution_start` / 阶段切换 | `step` + `tool` |
| `done` | `agent_settled` 且产物校验通过 | `done` + `artifact` |
| `info` | `message_update/text_delta`（节流）/ 数据文件清单 | `info` |
| `warn` | 质量门 Issue / `auto_retry_start` | `warn` + `Issue[]` |
| `complete` | 四阶段全部 `agent_settled` | `complete` + `RunSummary` |
| `error` | `abort` / `extension_error` / 超时 | `error` |
| `ping` | —（30s 心跳） | `ping` |
| —（v1.1 新增） | `thinking_start` / `_delta` / `_end` | `thinking`（`contentIndex` 重建，`thinking_end.content` 覆盖） |
| —（v1.1 新增） | `text_*` / `toolcall_*` | `output` / `tool` |
| —（v1.1 新增） | `turn_start` / `turn_end` | `turn` |
| —（v1.1 新增） | `message_update.usage` | `usage`（token / cost，按任务与全局两级汇总） |
| —（v1.1 新增） | `thinking_level_changed` / `session_info_changed` | `model` |
| —（v1.1 新增） | `agent_start` / `agent_end` / `compaction_*` / `auto_retry_*` | `lifecycle`（`agent_end` **不**产生 `done`） |
| —（编排层发出） | — | `stage` / `barrier`（四阶段 DAG，Pi 无对应事件） |

> 参考 Pi JSON 事件流：`agent_end` 表示一次低层 run 结束，**其后仍可能自动重试/压缩重试**；`agent_settled` 才表示 Pi 不会再自动继续。流式重建三条铁律：① `contentIndex` 关联同一内容块；② `*_end` 的 `content` 是权威值，覆盖 `*_delta` 拼接；③ `message_end.message` 覆盖整个 partial 消息。WebUI 的思考过程视图与刷新回放都依赖这三条。

## 附录 D：参考资料

- Pi 官网与文档：<https://pi.dev/>、<https://pi.dev/docs/latest>（SDK / Extensions / Skills / Prompt Templates / Packages / JSON / RPC / CLI Integration / Security）
- **v1.1 重点核对**：[Choose a Model](https://pi.dev/docs/latest/models)（`/model`、`/thinking`、`/scoped-models`、`models.json`）、[Providers](https://pi.dev/docs/latest/providers)（凭据与环境变量）、[Settings Reference](https://pi.dev/docs/latest/settings)（7 档 thinking / `defaultTools` / compaction）、[Message Types](https://pi.dev/docs/latest/message-types)（`ThinkingContent` / `Usage` / `AssistantMessage`）、[JSON Event Stream](https://pi.dev/docs/latest/json)（`thinking_*` / `turn_*` / `usage` / `agent_settled`）、[SDK](https://pi.dev/docs/latest/sdk)
- Pi 仓库：<https://github.com/earendil-works/pi>，`packages/coding-agent/docs/*`、`examples/sdk/*`（01/03/05/06/08/11/12/14）、`examples/extensions/subagent/`
- SDK 关键示例：`03-custom-prompt.ts`（systemPromptOverride）、`05-tools.ts`（工具白名单 + cwd）、`06-extensions.ts`（DefaultResourceLoader + extensionFactories）
- 源项目：<https://github.com/LosAveRoad/SolveX>
- 源项目自带缺陷清单：`docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md`
- 备选编排包：`pi-agents`(<https://www.npmjs.com/package/pi-agents>)、`@groeponline/pi-agent-orchestrator`(<https://www.npmjs.com/package/@groeponline/pi-agent-orchestrator>)

---

**状态：v1.1 设计规格已按用户确认更新（D1/D2/D6 已定，D3/D4/D5 按推荐默认执行并已详解，WebUI 2.0 规格见 §10）。** 可直接按 `SolveX-Pi-Migration-Plan.md` 阶段 0 开工；执行纪律遵循 superpowers：先规格 → 再计划 → TDD（RED-GREEN-REFACTOR）→ 逐任务代码评审 → 完成前验证。剩余唯一需要人工准备的是 Node ≥ 22.19 与至少一个可用模型凭据（计划 PRE-2 / PRE-3）。
