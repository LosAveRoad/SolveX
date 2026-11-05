# ADR-0005：Critical 问题默认告警、可选阻断（D4 推荐方案 A）

- 状态：已接受（2026-11-05）
- 决策：两种模式**都有 P2→P3 强制质量门**；区别只在发现 Critical 后停不停。默认 `strict=false`：只 `warn`，继续进入 P4（与旧版「一次跑完」一致，避免单个模型的图片规格问题让整批并行长跑失败）。`--strict` / Web 严格模式开关：Critical 阻断进入 P4。
- 实现：`gates/validateModelOutput.ts` 返回结构化 `Issue{code,severity,evidence}`；P3 节点前检查；调度器在 `failed` 前置节点时阻断下游。
- 影响：CLI `--strict`、`POST /api/run` 的 `strict` 字段、`RunSummary.issues`、WebUI 严格模式复选框。
- 验证：`test/flow/pipeline.test.ts` 的 strict / 非 strict 双路径 + T6.10 回归。
