# ADR-0010：一道题一个工作区、多次运行互不覆盖

- 状态：Accepted
- 日期：2026-11-06
- 触发：WebUI 进入「文件优先」形态后，工作区（题目）与运行（session）两层语义混杂，且同一题目无法保留多次可对比的独立运行

## 现象与证据

改造前的 `apps/web/src/runner.ts` / `workspaces.ts`：

1. 所有 run 平铺在 `~/.solvex/sessions/{id}/`，工作区只存在于 `~/.solvex/workspaces/{id}/inputs/`，两者靠 `.solvex-meta.json` 里的 `workspaceId` **反向**关联。删掉或迁移工作区目录后，产物仍散落别处。
2. `POST /api/workspaces/:id/run` 用 `starting` 集合 + `registry.isRunning()` 直接拒绝第二个请求（409）。同一题目想换模型/换并发重跑，只能等上一次结束。
3. 启动运行不接受任何参数，`ModelConfig` 在 `create()` 时从全局 `~/.solvex/config.json` 读一次。改了全局设置后，历史 run 用的是什么配置无从查证，也无法复现。
4. 前端把「当前 run 在跑」当成全局状态：顶部按钮从「开始建模」变成「停止运行」，运行记录里的其他 run 状态不刷新。

## 决策

1. **目录契约**：`workspaces/{workspaceId}/` 只保存输入（`inputs/`、`workspace.json`）与 `runs/`；每次运行一个 `runs/{runId}/`，内含完整的 `00_problem / data / 01_modeling / 02_programming / 04_paper`、`events.jsonl`、`runtime.json`。`runId` 用 UUID，保证并行启动不撞目录。旧 `sessions/` 保持**只读兼容**：`listAllRuns()` / `findRun()` 同时索引新布局与旧平铺目录，不迁移、不删除历史数据。
2. **允许并行**：移除 409 与 `starting` 集合。每个 run 独享 `EventBus`、`AbortController`、事件日志、阶段快照、产物目录和 ZIP；`POST /api/abort/:id` 只作用于该 run。工作区输入在启动瞬间被快照进 run 的 `00_problem/` 与 `data/`，之后改输入不回溯影响已有 run。
3. **runtime 快照**：启动时可传白名单覆盖（`defaults` / `byPhase` / `scopedModels` / `concurrency` / `strict` / `persistThinking`），与全局配置合并后写入该 run 的 `runtime.json`。`sanitizeOverrides()` 丢弃未知字段、非法 thinking 档位和任何疑似凭据；`runtime.json` 不含 `credentials` / `endpoints` / `apiKey`。`SolveXFlow` 消费的是这份逐 run 生效配置，后续改全局设置不影响历史 run。
4. **前端对齐**：运行记录列表展示每次运行的 runtime 摘要与实时状态（轮询 `/api/workspaces/:id/runs`）；「新建运行」按钮在任何时候都可用；「停止本次运行」只对选中的 run 生效；切换 run 时重置 transcript / stages / usage，不串状态；产物、下载、SSE、回放全部按 `runId` 索引。

## API

| 端点 | 语义 |
| --- | --- |
| `POST /api/workspaces/:id/runs` | 新建一次运行；body 可为 `{ runtime: {...} }` 或直接的覆盖对象 |
| `POST /api/workspaces/:id/run` | 旧路径别名，语义同上（不再返回 409） |
| `GET /api/workspaces/:id/runs` | 该题目的全部运行，倒序，含 `runtime` 摘要 |
| `GET /api/workspaces/:id/runs/:runId` | 运行详情 + 完整快照；跨工作区访问返回 404 |
| `GET /api/runs/:id` / `GET /api/runs/:id/runtime` | 按 runId 直接查详情 / 快照 |
| `GET /api/sessions` / `POST /api/run` | 旧版保持兼容；无 workspaceId 时仍写 `sessions/` |

## 后果

- 一个题目可以有 N 个并存、可对比、可回放的 run；产物/事件/配置/取消状态物理隔离。
- 磁盘占用随运行次数线性增长（每次运行都快照输入），需要清理策略时按 `runs/` 子目录粒度删除即可，不影响其他 run。
- `ModelRuntime` 仍是进程级单例（只持有 catalog 与凭据），**不同 run 的区别在配置快照与 `RunRequest` 的模型/thinking/并发参数**，不是每个 run 各起一个 SDK 实例；若未来要按 run 隔离凭据，需另做设计。
- 测试基线：`test/workspace-runs.test.ts`（目录/索引/快照/隔离）、`test/web/workspaces.test.ts`（并行启动、跨工作区 404、旧 API 兼容）、`test/web/runs-view.test.ts`（前端纯视图模型）。
