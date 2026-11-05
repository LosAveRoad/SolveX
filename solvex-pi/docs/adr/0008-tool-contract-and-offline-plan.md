# ADR-0008：工具契约与 P1 离线执行策略

- 状态：Accepted
- 日期：2026-11-05
- 触发：真实模型（DeepSeek）端到端跑 2026 MCM Problem C 时暴露的两个问题

## 现象

1. P1 阶段模型从不调用 `write`，`01_modeling/master_plan.md` 始终不落盘。
2. 模型反复用 `bash` + `curl` 请求 arxiv，出现 `The read operation timed out` 后无限重试。
   单次运行产生 13k+ 事件、0 个产物，只能人工中止。
   在输入里临时加上「禁止联网、首个动作必须 write」的约束后，P1 立刻产出文档，
   后续阶段也顺利写出 `model1_recovery.py` / `fan_vote_estimates.csv` 等真实产物。

## 根因

- Pi SDK 1.5.0 只注册 7 个内置工具：`read / grep / find / ls / bash / write / edit`。
- `ROLE_TOOLS.modeling` 与逐字提示词仍声明旧 Python 运行时的
  `arxiv_search / web_search / webReader`。`buildCustomTools()` 里这三个只是返回
  `"...Configure MCP for live results."` 假结果的 placeholder，而且 CLI / Web 构造
  `PiAgentRunner` 时都没有传 `customTools`，它们从未进入 session。
- 逐字资产 `modeling.system.md` 的第 2 步是 `SEARCH (strongly recommended)`，
  第 5 步才是 `WRITE`；`PLAN_TEMPLATE` 也含 `search for relevant methods`。
  模型按提示去检索 → 工具不存在 → 用 `bash` 模拟联网 → 超时重试 → 永远到不了 WRITE。
- 既有测试只校验「提示词提到的名字在白名单里」和「白名单标识符格式合法」，
  从未校验工具是否真实注册，因此这类静默失效一直没被发现。

## 决策

1. **单一工具契约**：`SDK_BUILTIN_TOOLS` + `CUSTOM_TOOL_NAMES` = `AVAILABLE_TOOLS`，
   `ROLE_TOOLS` 必须是其子集；`validateRoleTools()` 供测试与运行时校验。
2. **移除幽灵工具**：从 modeling 白名单和 `buildCustomTools()` 删除三个占位检索工具。
   将来需要联网检索时以 MCP 单独接入，并显式登记到 `AVAILABLE_TOOLS`。
3. **接线**：`PiAgentRunner` 默认注入 `buildCustomTools()`，并按契约过滤未知工具，
   让 `python_execute` 真正可用，同时杜绝「白名单写了但 session 没有」。
4. **运行时执行策略**：逐字提示词资产（`modeling.system.md`、`PLAN_TEMPLATE` 常量）
   一个字不改，沿用 `HANDOFF_HINT` 的「追加而非改写」模式，在 `modelingSystem()` /
   `renderPlan()` / `renderPlanRetry()` 输出末尾追加 `OFFLINE_PLAN_POLICY`：
   明确检索工具不可用、禁止用 `bash/curl/wget/pip` 模拟联网、`write` 是首个动作、
   文件写完即停。T1.2 逐字快照因此继续成立。

## 后果

- P1 不再因联网检索空转；`write` 成为显式首选动作，规划产物可预期落盘。
- 逐字迁移承诺保持：磁盘上的 `.md` 资产与内联模板常量均未改动，
  差异全部集中在运行时拼接层，可单独审计与回滚。
- `customTools` 现在总是注入，`python_execute` 在 CLI 与 WebUI 中一致可用。
- 新增回归测试 `test/prompts/tool-contract.test.ts`，把「白名单 ⊆ 运行时工具」
  变成硬断言，防止同类漂移再次发生。
- 已知遗留：`safetyExtension`（R5/R11 路径拦截）仍未注入 `extensionFactories`，
  属于同类「声明未接线」问题，建议单独提交处理，本 ADR 不扩大改动面。
