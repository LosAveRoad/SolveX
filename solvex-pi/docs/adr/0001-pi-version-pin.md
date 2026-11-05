# ADR-0001：Pi SDK 精确版本锁定

- 状态：已接受（2026-11-05）
- 背景：Pi 迭代快，包名从 `@mariozechner/*` 迁到 `@earendil-works/*`；设计文档 R1 要求锁精确版本。
- 决策：`@earendil-works/pi-coding-agent` **精确锁定 `1.5.0`**（安装当天 npm latest，实测 `engines.node >=22.19.0`）。
  其传递依赖 `typebox` 亦锁 `1.3.27`（与 SDK 的 dependencies 完全一致，避免双份 schema 实现）。
- 后果：升级 SDK 需单独提交并跑 `pnpm run check` + 阶段 3 集成测试；`packages/pi-runtime` 是唯一 import 点，breaking change 不外溢。
- 环境：Node 由 22.13.1 升级到 **22.20.0**（`.nvmrc` / `engines` 同步），PRE-2 已完成。
- 实测导出：`createAgentSession` / `SessionManager` / `DefaultResourceLoader` / `ModelRuntime` / `AuthStorage` 均存在。
