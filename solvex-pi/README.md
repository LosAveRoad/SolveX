# SolveX 2.0 — 基于 Pi coding-agent SDK 的多模型数学建模流水线

> 产品形态：**带 WebUI 的 CLI 工具**。旧 Python 自研运行时（`ToolCallAgent` / `llm.py` / `ToolCollection` / `compact.py`）已全部移除，四阶段编排模式与提示词资产 100% 保留。

## 架构

```
apps/cli ─┐
apps/web ─┼─→ @solvex/core（零 Pi 依赖，AgentRunner 端口倒置）
          │      ├─ prompts/        逐字迁移的提示词（唯一真源）
          │      ├─ flow/           四阶段状态机 + 并行 DAG + 屏障
          │      ├─ contracts/      masterPlan / verdict / handoff
          │      ├─ gates/          质量门
          │      └─ events/         SolveXEvent v1.1 契约 + EventBus
          └─→ @solvex/pi-runtime（唯一 import @earendil-works/* 处）
                 ├─ PiAgentRunner  一阶段一 createAgentSession()
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
npx tsx apps/cli/src/index.ts run -p problem.md -d data/ --concurrency 3

# 续跑 / 只写论文 / 质量门
npx tsx apps/cli/src/index.ts run --resume <session_id> --from-model 2
npx tsx apps/cli/src/index.ts run --skip-to-writing -r <session_id>
npx tsx apps/cli/src/index.ts validate <session_id>
npx tsx apps/cli/src/index.ts inspect <session_id>

# 启动 WebUI 2.0（只绑定 127.0.0.1）
npx tsx apps/cli/src/index.ts serve --port 8000

# 凭据在 WebUI「模型设置」中配置；CLI 与 WebUI 始终使用真实模型运行时
```

参数与旧版 `run_flow.py` 1:1 兼容，新增 `--concurrency N` / `--strict` / `--session-dir`；未提供演示模式，未知选项会直接报错。
`--strict` 对应 D4：质量门发现 Critical 问题时阻断进入 P4（默认关闭，只告警）。

## Workspace WebUI

The browser UI now uses the real `@earendil-works/pi-web-ui` components. Select a
workspace, upload a PDF/DOCX/MD/TXT problem and data, then start modeling. No chat
message is required. See [workspace WebUI guide](docs/webui-workspaces.md).

Build before starting: `npm run build:web`. The existing modeling pipeline and
API remain available.

### Existing runtime features

浏览器打开 `http://127.0.0.1:8000/`，详见 `docs/webui-2.0.md`：

- **模型配置中心**：按 provider 分组、搜索、能力标签、设为默认、按阶段分档、循环模型集、thinking 档位按模型能力裁剪、运行时注入 Key（只进内存）、自定义 OpenAI 兼容端点。凭据**只回 `masked`**。
- **思考过程视图**：`thinking_start/_delta/_end` 按 `contentIndex` 流式重建，`*_end.content` 权威覆盖，默认折叠可展开，`redacted` 降级，64KB 截断，与产物严格隔离。
- **运行阶段视图**：外层 `stage`/`barrier`（编排层权威）+ 内层 `turn`/`tool`/`thinking`/`output`（Pi 会话细节），并行节点独立刷新，屏障显示 `3/5`。
- **顶部实时用量条**：模型 / thinking 档 / token / ¥；SSE `Last-Event-ID` 续传 + `/api/events` + `/api/stages` 刷新回放。

14 个 API 端点见设计文档 §10.8；旧 4 个端点保持兼容（含 multipart 上传修复与真实产物树）。

## 配置

- 端点：`packages/pi-runtime/models.json`（密钥写成 `$VAR` / `${VAR}` 环境变量引用，禁止明文；`models` 必须是含 `id` 的对象数组，符合 Pi SDK 1.5.0 schema）。
- 运行配置：`~/.solvex/config.json`（`defaults` / `byPhase` / `scopedModels` / `concurrency` / `strict` / `persistThinking`）。WebUI 可直接编辑并保存即刷新。
- 会话产物：`~/.solvex/sessions/{id}/`（目录契约与旧版完全一致，见设计文档 §2.5）。

## 测试

```bash
npm run check                 # tsc + vitest
npx vitest run                # 218 passed / 1 skipped（真实模型集成需 PI_TEST_MODEL）
PI_TEST_MODEL=<provider/id> npx vitest run test/pi/integration.test.ts
```

`test/` 分层：`prompts`（逐字快照）、`flow`（并行 DAG / 四阶段 / resume / abort）、`gates`、`pi`（事件桥接 / 适配器 / 模型运行时）、`web`（14 端点 / SSE / store 三视图）、`cli`、`regression`（23 个旧问题）。

## 文档

| 文件 | 内容 |
| --- | --- |
| `SolveX-Pi-Migration.md` | 迁移设计规格 v1.1（现状盘点、目标架构、ADR、风险、验收基线） |
| `SolveX-Pi-Migration-Plan.md` | 9 阶段实施计划（TDD 任务粒度） |
| `docs/MIGRATION-STATUS.md` | **本次实施完成状态 + Go/No-Go 清单** |
| `docs/regression-report.md` | 23 个旧问题逐条结论 |
| `docs/webui-2.0.md` | WebUI 使用说明 |
| `docs/benchmark.md` | 性能与成本基线 |
| `docs/adr/*.md` | 关键决策记录 |
