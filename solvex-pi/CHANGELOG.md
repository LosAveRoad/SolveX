# Changelog

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
