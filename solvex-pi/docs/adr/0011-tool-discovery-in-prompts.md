# ADR-0011：工具清单由代码发现，提示词不再自带工具版本

- 状态：Accepted
- 日期：2026-11-06
- 关联：ADR-0008（幽灵工具 / 离线策略）、ADR-0009（运行时策略追加）
- 影响资产：`packages/core/src/prompts/modeling.system.md`

## 现象与证据

`modeling.system.md` 从旧 Python 版逐字迁移而来，开头写着一份 `AVAILABLE TOOLS:`：

```
- arxiv_search: Search ArXiv ...
- web_search: Search the web ...
- webReader: Read and extract content from any URL.
- python_execute: ...
- write/edit: ...
```

加上 WORKFLOW 第 2 步 `SEARCH (strongly recommended)`，这份清单**同时声明了三个
运行时并不存在的工具**。ADR-0008 用「追加一段 OFFLINE_PLAN_POLICY 覆盖说明」压住了
症状（模型用 `bash + curl` 联网超时、无限重试、P1 不落盘），但没有消除根因：

- 每次 SDK 升级、工具增减或角色白名单调整，都要人肉同步提示词文本；
- 「提示词版本」与「运行时工具版本」必然漂移，覆盖策略越写越长；
- 覆盖策略本身又硬编码了 `write` / `bash` / `curl`，形成第二份清单。

## 决策

1. **提示词资产不再声明工具**。`modeling.system.md` 的 `AVAILABLE TOOLS:` 段换成
   单个占位符 `{{AVAILABLE_TOOLS}}`；WORKFLOW 的 `SEARCH` 步改成离线的 `METHODS` 步，
   其余工具名（含 `python_execute`、`write/edit`）改成「the available tools」。
   SETTING / RESPONSE FORMAT / PHILOSOPHY / MASTER PLAN FORMAT / IMPORTANT RULES
   逐字不动（由 `test/prompts/modeling.test.ts` 的章节级基线断言守着）。
2. **代码发现**。新增 `packages/core/src/prompts/toolCatalog.ts`（`ToolDescriptor`、
   `renderToolList` / `injectToolList` / `toolDescriptorsFor`）与
   `packages/pi-runtime/src/toolDiscovery.ts`：
   - 内置工具从**已安装 SDK 自己的注册表**读：`dist/core/tools/index.js` 的
     `allToolNames` + `createToolDefinition(name, cwd).promptSnippet/description`；
   - 自定义工具从 `buildCustomTools()` 的 `name/description` 读；
   - 结果按进程缓存；SDK 内部路径变动时回落到 `SDK_BUILTIN_TOOLS`（仍是代码，
     绝不回落到提示词文本）。
3. **注入点在真正注册工具的那一层**。`PiAgentRunner.run()` 先用发现结果过滤
   `req.tools`，再用「同一批名字」生成清单注入 `systemPromptOverride`。于是
   **提示词里的工具列表 ≡ 本次 session 的 `options.tools`**，物理上不可能漂移。
   清单末尾明确「只调用列出的工具，不要模拟不存在的工具」。
4. **`OFFLINE_PLAN_POLICY` 去工具名化**。只保留「离线 + 首动作落盘 + 写完即停」
   的执行约束，不再复述 `arxiv_search` / `write` 等名字，也不再自称「覆盖上面的工具说明」。
5. **历史基线不删**。`docs/legacy-prompts/expected-r2.json` 与 `modeling.py` 保持原样，
   作为迁移期证据；T1.2 快照从「全文相等」改为「除工具段与 WORKFLOW 外逐字相等」，
   并新增「资产里不得出现工具名/工具清单式声明」的反向断言。

## 后果

- 工具增减只需改注册代码；提示词文件不用跟着发版，也不会出现幽灵工具。
- 发现结果里 SDK 还有 `powershell`，但该角色白名单没选它，所以它既不在 session
  的 `tools`、也不在该角色的提示词里 —— 这正是「同一批名字」的效果。
- `validateRoleTools()` 仍有意义（守角色白名单），但不再是唯一防线；
  `test/prompts/tool-discovery.test.ts` 直接断言「注入的名字集合 == createOptions.tools」。
- 其它 `.md` 资产（`programming.system.md` 等）与 `RESULTS_CONTRACT` /
  `WORKSPACE_DISCOVERY_POLICY` 里的工具名暂未清理。它们是代码策略或尚未接入占位符
  的资产，且受 `validateRoleTools()` 约束；后续可按同一机制逐个替换占位符。
- `FakeAgentRunner` 不注入（它不向模型发送 prompt），因此测试流程里可能看到未替换的
  占位符，属预期；生产路径永远走 `PiAgentRunner`。
- 代价：依赖 SDK 内部模块路径 `dist/core/tools/index.js`。SDK 精确锁 1.5.0，
  且发现失败有代码级回落；升级 SDK 时 `SDK_TOOLS_MODULE_PATH` 测试会提示路径变化。
