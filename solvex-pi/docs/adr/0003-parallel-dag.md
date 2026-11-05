# ADR-0003：无依赖即并行的 DAG 调度（D2 已确认）

- 状态：已接受（2026-11-05）
- 决策：`P1 → barrier(master_plan) → P2-IMPL fork N【并行】 → barrier(all-results) → P2-REVIEW fork N【并行】 → barrier(reviews) → P3（纯代码）→ P4`。只在真实数据依赖处串行。
- 实现：`packages/core/src/flow/{dag.ts, scheduler.ts}`，纯函数 + Promise 池 + 屏障计数器，**零 Pi 依赖**，用 `FakeAgentRunner` 完整 TDD。并发上限 `concurrency`（默认 3，`=1` 等价旧版串行作回归对照）。
- 写冲突根除（R11）：`all_results_summary.md` 只由 P3 纯代码在屏障后生成；`master_plan.md` 全程只读；每个任务 `RunRequest.writablePrefixes` 只含自己的 `02_programming/model_n/`；扩展 `tool_call` 拦截越界写入。
- 失败隔离：单任务失败标红但不取消兄弟；屏障处汇总 `completed/total`；**线性依赖链上前置 `failed` 会阻断下游**（strict 质量门靠此阻止 P4）。
- 取消传播：`AbortController` 共享 signal 给所有在跑 session，已落盘产物不损坏。
- 验证：`test/flow/scheduler.test.ts` 7 条断言 + `test/regression/legacy-issues.test.ts` 的 `concurrency=1` 与 `=3` 产物逐字节一致。
