# 迁移实施完成状态（2026-11-05）

> 配套：`SolveX-Pi-Migration.md` v1.1（设计规格）、`SolveX-Pi-Migration-Plan.md`（实施计划）。
> 结论：**有条件 Go** —— 代码、测试、文档与可运行演示全部就绪；最终 Go/No-Go 待真实模型凭据补齐后签字。

## 检查点达成

| 检查点 | 目标 | 状态 | 证据 |
| --- | --- | --- | --- |
| CP0 | 工程基线、事件契约、配置骨架 | ✅ | `npm run check` 绿；Node 22.20.0；SDK 精确锁 1.5.0 |
| CP1 | 提示词逐字迁移（最高优先级） | ✅ | 10 个 `.py` + 5 段内联归档；`expected-r2.json` 逐字比对；仅 R-2 白名单替换 |
| CP2 | core 编排引擎（零 Pi 依赖）+ 并行 DAG | ✅ | FakeRunner 在 0 次模型调用下跑通四阶段；`concurrency=1/3` |
| CP3 | Pi SDK 适配层 | ✅ | `PiAgentRunner` / `eventBridge` / `modelRuntime`；mock 单测全绿 |
| CP4 | CLI 1:1 兼容 | ✅ | `run/inspect/validate/serve` 端到端子进程测试通过 |
| CP5A | WebUI 2.0 后端 14 端点 + SSE | ✅ | `app.inject()` 端点测试 + 真实 HTTP SSE 测试 |
| CP5B | WebUI 2.0 前端三视图 | ✅ | 66 个纯函数测试；store 重建三原则 |
| CP6 | 23 问题回归 + 并行/写安全 | ✅ | `docs/regression-report.md` 逐条结论 |
| CP7 | 端到端验收 | ⚠️ 部分 | HTTP 端到端演示通过；真实模型/Playwright 录屏待补 |
| 阶段 8 | 清理与发布 | ✅ | 本仓库为纯 TS monorepo，无 Python 残留；归档/ADR/文档齐备 |

## 测试基线

```
Test Files  36 passed | 1 skipped (37)
Tests       218 passed | 1 skipped (219)
typecheck   tsc -p tsconfig.base.json --noEmit  ✅
```

唯一 skip 项：`test/pi/integration.test.ts`（需 `PI_TEST_MODEL` 真实模型凭据，PRE-3）。

## 历史端到端演示实测（内部测试 runner，2.0.3 起已不对用户开放）

- 一次完整运行产出 **216 个 SSE 事件**，覆盖 15 种类型（thinking=40 / stage=20 / usage=8 / barrier=6 / complete=1）。
- 阶段 DAG 11 个节点、34 个产物文件（含上传的 `data/data.csv`）、ZIP 下载合法、凭据响应无 `sk-`。
- 详见 `docs/benchmark.md`。

## 完成定义（DoD）逐条

| # | 条目 | 状态 |
| --- | --- | --- |
| 1 | §8.1 功能验收 13 项 | ✅（WebUI 三能力经 HTTP 端点 + 纯函数测试验证） |
| 2 | §8.2 质量门 11 项、23 个旧问题逐条结论 | ✅ `docs/regression-report.md`（18 已解决 / 5 缓解） |
| 3 | §8.3 非功能：core 零 SDK 依赖、typecheck/test 绿、提示词逐字、并行分支、事件契约、凭据脱敏 | ✅ 静态检查断言 + 专项测试 |
| 4 | 提示词资产 100% 归档与快照测试 | ✅ `docs/legacy-prompts/` + `test/prompts/` |
| 5 | CLI 参数与 Web API 兼容（含 resume / skip-to-writing / --concurrency） | ✅ |
| 6 | WebUI 2.0 三能力可演示 | ✅ HTTP 端到端（录屏待补） |
| 7 | 并行：`concurrency=1` 与 `=3` 产物逐字节一致；无 LLM 写共享文件 | ✅ T6.13 |
| 8 | 仓库中不再存在自研 LLM 调用 / Agent Loop / 工具集合 / 上下文压缩 | ✅ 新仓库为纯 TS；静态检查断言 |
| 9 | 不做 `pi-package/`，提示词单一真源 | ✅ |
| 10 | README / ADR / 回归报告 / benchmark / WebUI 说明齐备 | ✅ |
| 11 | Go/No-Go 评审签字 | ⚠️ 待真实凭据（见下） |
| 12 | 覆盖率 ≥85% | ⚠️ 以本次实测为准（见 `docs/benchmark.md` / 覆盖率报告） |
| 13 | 旧 Python 代码删除 / 归档 | ✅ 本仓库从零构建，旧代码仅存于 `docs/legacy-prompts/` 归档 |

## 保留项（Go/No-Go 之前必须处理）

1. **PRE-3 模型凭据缺失**：真实模型 P1 集成、2025 C 夹具端到端（T7.1）、真实成本/耗时基线（T7.2）未跑。
   补齐方式：配置一个 provider 的 Key 或 OAuth → `PI_TEST_MODEL=<provider/id> npx vitest run test/pi/integration.test.ts` → `solvex run -p <夹具> -d <数据>`。
2. **Playwright 浏览器录屏**（T5.21 / T7.7）未做：已用「HTTP 端到端 + 前端 66 个纯函数测试 + 真实 SSE 流」替代验证；如需正式验收录屏，补一次浏览器冒烟。
3. **「缓解」类 5 个问题的最终效果**依赖真实模型行为，需用真实夹具人工复核（A1/A3/B1/B3/C3/D2）。
4. **SDK 版本**：按 ADR-0001 锁 `1.5.0`；升级需单独提交并跑全套测试。实测 SDK 与初稿文档的三处偏差已在 `modelRuntime.ts` / `PiAgentRunner.ts` 适配（见 ADR-0006）。

## 关键实施偏差记录（相对 v1.1 设计文档）

| 项 | 文档初稿 | SDK 1.5.0 实测 | 处置 |
| --- | --- | --- | --- |
| SDK 版本 | 占位 `0.81.1` | latest `1.5.0` | 精确锁 1.5.0（ADR-0001） |
| `typebox` | `0.34.x` / `Type.Object` | `1.3.27` 扁平 API `Object({code:String()})` | 适配（`extensions/solvex-tools.ts`） |
| `createAgentSession.model` | `{provider,id}` | `Model` 对象，需 `getModel()` 解析 | `ModelRuntimeManager.resolve()` |
| `scopedModels` | `string[]` | `{model: Model}[]` | `scopedModels()` 转换 |
| `AuthStorage` / `InlineExtension` | 文档提及 | 未导出 | 改用 `ModelRuntime` / `extensionFactories` |
| Node | 22.13.1 | 要求 ≥22.19 | 升级 22.20.0（PRE-2 完成） |
