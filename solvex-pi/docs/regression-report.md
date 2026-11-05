# 回归报告：旧管线 23 个问题逐条结论

> 依据：`docs/legacy-prompts/` 归档与 `docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md`（已随源码归档）
> 验证：`test/regression/legacy-issues.test.ts` + 各阶段专项测试，全部随 `npm test` 运行。

## 结论汇总

| 类别 | 数量 | 已解决 | 缓解 | 需人工复核 |
| --- | --- | --- | --- | --- |
| A 建模 Agent | 3 | 2 | 1 | 0 |
| B 编程 Agent | 5 | 4 | 1 | 0 |
| C 评审 Agent | 3 | 2 | 1 | 0 |
| D 写作 Agent | 5 | 3 | 2 | 0 |
| E 编排 | 4 | 4 | 0 | 0 |
| F 基础设施 | 3 | 3 | 0 | 0 |
| **合计** | **23** | **18** | **5** | **0** |

## 逐条明细

| ID | 问题 | 根因归属 | 新架构处置 | 结论 | 验证 |
| --- | --- | --- | --- | --- | --- |
| A1 | 计划过于理想化（环境无 PyMC/PyTorch） | 提示词 | 提示词逐字保留 + 阶段隔离 + 质量门；模型可行性仍依赖模型判断 | 缓解 | 提示词快照 |
| A2 | 评审覆写 `master_plan.md` | 流程保护 | 评审只读工具白名单 + 字节快照双保险 | 已解决 | `pipeline.test.ts` / T6.1 |
| A3 | 无时间预算，5 个模型跑不完 | 提示词/流程 | 按角色 `maxTurns`（25/30/40）+ 无全局硬杀 | 缓解 | T6.8 |
| B1 | 编程 Agent 早期步骤浪费 | 运行时 | 一阶段一 session + 提示词「每次只调一个工具」软约束 | 缓解 | 提示词快照 |
| B2 | 兜底摘要泄漏 `<think/>` 与原始工具输出 | 产物契约 | `ensureSummary()` 只写结构化占位 | 已解决 | `ensureSummary.test.ts` / T6.2 |
| B3 | 预测数值量级错误 | 产物契约 | 评审数值 sanity 判据 + 提示词 CROSS-CHECK | 缓解 | 提示词快照 |
| B4 | 概率未校准（37 国 >0.99，总和 62） | 质量门 | `PROBABILITY_SUM_OUT_OF_RANGE` / `UNCALIBRATED_PROBABILITIES` 结构化 Issue | 已解决 | `validateModelOutput.test.ts` / T6.3 |
| B5 | `results_summary` 格式不统一（根因起点） | 产物契约 | `validateSummaryShape()` 六小节校验 + `handoff.json` 双轨 | 已解决 | T6.4 |
| C1 | 评审文件根本没生成 | 决策协议 | P2-REVIEW 强制产出 `{model}_review.md` + 双标记 | 已解决 | T6.5 |
| C2 | 评审没抓到 B4 | 决策协议 | 质量门结构化 Issue 独立于评审；评审注入完整结果 | 已解决 | T6.3 |
| C3 | 评审提示词太泛 | 决策协议 | `REVIEW_PROMPT` 4 项判据 + `## Fix Instructions:` | 缓解 | `modeling.test.ts` |
| D1 | 抄错数值 | 上下文传递 | `writing` 提示词 `USE ONLY the results provided` | 已解决 | T6.6 |
| D2 | 两模型表完全相同 | 提示词 | 提示词要求 `Note: both models converge` | 缓解 | 提示词快照 |
| D3 | 摘要与结论矛盾 | 提示词 | `WRITE ORDER: ... abstract LAST` | 已解决 | T6.7 |
| D4 | 编造 MAE=2.1 等指标 | 提示词 | `ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE)` 区段 | 已解决 | T6.6 |
| D5 | 编造未实现模型的内容 | 上下文传递 | `figureInfo()` 只列磁盘上真实存在的图 | 缓解 | `stages.ts` |
| E1 | 1h 全局超时太紧 | 编排层 | 按阶段独立预算，不存在全局 3600s 硬杀 | 已解决 | T6.8 |
| E2 | Web 重跑/resume 清理已有产物 | 编排层 | `prepareWorkspace({mode:"resume"})` 只读不删 | 已解决 | `workspace.test.ts` / T6.9 |
| E3 | 阶段间无验证门 | 编排层 | P2→P3 强制 `validateModelOutput()` + `--strict` | 已解决 | T6.10 |
| E4 | 兜底摘要污染 | 编排层 | `ensureSummary()` 不塞工具输出 | 已解决 | T6.2 |
| F1 | DeepSeek Reasoner 单次 80K 导致下轮 BadRequest | 自研运行时 | 一阶段一 `createAgentSession()` 天然隔离上下文 | 已解决 | `PiAgentRunner.test.ts` |
| F2 | 压缩后质量下降 | 自研运行时 | Pi 内置 compaction，删除 `compact.py` | 已解决 | 静态检查（core 零运行时残留） |
| F3 | 无文件保护 | 自研运行时 | 只读白名单 + `writablePrefixes` 越界拦截 | 已解决 | T6.1 / T6.13 |

## v1.1 追加回归

| 项 | 内容 | 结论 | 验证 |
| --- | --- | --- | --- |
| T6.12 | `handoff.json` 双轨：无结构化文件的旧 session 仍能跑完 | 通过 | `legacy-issues.test.ts` |
| T6.13 | 并行写安全：`concurrency=1` 与 `=3` 共享产物逐字节一致；无 LLM 写共享文件 | 通过 | `legacy-issues.test.ts` |
| T6.14 | 事件契约：`thinking_delta` 拼接 == `thinking_end.content`；`message_end` 覆盖；`agent_end` 不产生 `done`；`usage.reasoning` 不重复累加 | 通过 | `eventBridge.test.ts` / `web/store.test.ts` |
| Q-Web | 前端 `FormData` multipart（不设 JSON Content-Type）+ 真实产物树 | 通过 | `web/api.test.ts` / `web/artifacts.test.ts` |

> 「缓解」= 机制已到位，但最终效果依赖真实模型行为；需在 PRE-3 凭据就绪后用 2025 C 夹具人工复核。
