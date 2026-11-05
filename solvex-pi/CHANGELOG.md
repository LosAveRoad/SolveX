# Changelog

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
