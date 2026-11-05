# SolveX → Pi SDK 迁移实施计划（Migration Plan）

| 项目 | 内容 |
| --- | --- |
| 配套设计 | `SolveX-Pi-Migration.md` **v1.1**（本文所有 ADR / 编号均引用该文档；WebUI 规格见其 §10） |
| 版本 | v1.1（D1/D2/D6 已确认、并行编排、WebUI 2.0；与配套设计同步） |
| 方法论 | superpowers：先规格 → 再计划 → **强制 TDD（RED-GREEN-REFACTOR）** → 逐任务评审 → 完成前验证 |
| 执行单位 | 每个任务 2–5 分钟，含**精确文件路径、完整代码骨架、验证命令** |
| 硬规则 | 规格未确认不动手；没有先写失败的测试就不算实现；测试前写的代码一律删除；任一任务测试不通过不得进入下一任务 |
| 隔离 | 在 git worktree / 新分支 `refactor/pi-sdk` 上执行，主分支保持可发布 |

---

## 前置条件（阶段 0 之前必须由人完成）

| # | 事项 | 命令 / 检查 |
| --- | --- | --- |
| PRE-1 | **决策已确认**：D1 官方 SDK `@earendil-works/pi-coding-agent`、D2 无依赖即并行、D6 不做 `pi-package/`；D3/D4/D5 按设计文档 §9 推荐默认执行 | 已由用户确认，**不再阻塞开工**；本计划按此编写 |
| PRE-2 | 升级 Node 到 ≥ 22.19 | `node -v`（当前 22.13.1，需升级）；写入 `.nvmrc` 与 `engines` |
| PRE-3 | 准备模型凭据 | 至少一个可用 provider 的 API Key / OAuth；写入 `~/.pi/agent/` 或环境变量 |
| PRE-4 | 建立隔离工作区 | `git worktree add ../solvex-pi refactor/pi-sdk`；确认测试基线干净 |
| PRE-5 | 保存旧版黄金夹具 | 拷贝一份旧 session 产物（master_plan.md / results_summary.md / main.tex）到 `fixtures/legacy-session/`，作为回归基线 |
| PRE-6 | 确认 WebUI 2.0 验收口径 | 对照设计文档 §10 与 §8 F-8~F-13；准备可访问 `127.0.0.1` 的浏览器与一个支持 reasoning 的模型（用于思考过程验收） |

---

## 阶段总览

| 阶段 | 目标 | 关键产出 | 检查点 |
| --- | --- | --- | --- |
| **0** | 工程基线与护栏 | monorepo、TypeScript、vitest、**v1.1 事件契约**、配置骨架、Node 版本锁 | CP0：`npm test` 绿 |
| **1** | 提示词资产迁移（★ 最优先） | 全部 `.md` + 模板函数 + 快照测试 | CP1：逐字比对 100% 通过 |
| **2** | 核心编排引擎（零 Pi 依赖） | 四阶段状态机、**并行 DAG 调度器 + 屏障**、resume、gates、workspace、EventBus | CP2：FakeRunner 跑通全流程（含 `concurrency=1/3`） |
| **3** | Pi SDK 适配层 | `PiAgentRunner`、扩展工具、**模型配置桥接**、**thinking/turn/usage 事件桥接** | CP3：真实模型跑通单阶段，事件契约对齐 §4.6 |
| **4** | CLI | `solvex run` / `inspect` / `validate`（新增 `--concurrency`） | CP4：CLI 参数 1:1 兼容 |
| **5A** | **WebUI 2.0 后端** | 旧 4 端点 + 产物/回放/阶段/模型配置共 14 个端点 + SSE 全事件 | CP5A：API 与 SSE 测试全绿 |
| **5B** | **WebUI 2.0 前端** | 模型配置中心 / 思考过程 / 运行阶段三视图 + store 纯函数 | CP5B：浏览器端到端（§8 F-8~F-13） |
| **6** | 质量门与回归修复 | 结构化 handoff、评审只读化、23 问题 + 并行/写安全回归 | CP6：§8.2 全绿 |
| **7** | 端到端验收 | 2025 C 夹具跑通、并行性能/成本、WebUI 验收、文档 | CP7：Go/No-Go 评审 |
| **8** | 清理与发布 | 删除 Python 代码、归档、发版（**不做 pi-package**） | 完成 |

---

## 阶段 0：工程基线与护栏

### T0.1 初始化 monorepo

**文件**：`package.json`、`pnpm-workspace.yaml`、`tsconfig.base.json`、`.nvmrc`、`vitest.config.ts`

```jsonc
// package.json
{
  "name": "solvex",
  "private": true,
  "engines": { "node": ">=22.19.0" },
  "scripts": {
    "typecheck": "tsc -b --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "check": "npm run typecheck && npm test"
  },
  "devDependencies": { "typescript": "^5.9.3", "vitest": "^3", "@types/node": "^22" }
}
```

```yaml
# pnpm-workspace.yaml
packages:
  - "packages/*"
  - "apps/*"
```

**RED**：写 `test/smoke.test.ts` 断言 `engines.node` ≥ 22.19、workspace 包含 4 个包 → 运行失败（文件不存在）。
**GREEN**：创建上述文件。
**验证**：`node -v && pnpm install && npm run check` 全绿。

### T0.2 锁定 Pi SDK 版本（R1 缓解）

**文件**：`packages/pi-runtime/package.json`

**RED**：测试断言 `@earendil-works/pi-coding-agent` 为**精确版本**（非 `^`/`~`），且 `peerDependencies` 不含宿主包。
**GREEN**：

```jsonc
{
  "name": "@solvex/pi-runtime",
  "dependencies": { "@earendil-works/pi-coding-agent": "0.81.1" },
  "peerDependencies": {
    "@earendil-works/pi-coding-agent": "*",
    "@earendil-works/pi-ai": "*",
    "@earendil-works/pi-agent-core": "*",
    "typebox": "*"
  }
}
```

> 版本号按安装当天的实际 latest 固定，并在 `docs/adr/0001-pi-version-pin.md` 记录。Pi 迭代快，**禁止使用范围版本**。

**验证**：`pnpm install --frozen-lockfile && node -e "console.log(require('@earendil-works/pi-coding-agent').createAgentSession)"` 打印函数。

### T0.3 定义 `SolveXEvent` 与 `RunSummary` 类型

**文件**：`packages/core/src/events/types.ts`

**RED**：`test/events.test.ts` 断言事件联合类型可穷尽（用 `expectTypeOf` 或编译期断言）。
**GREEN**：按设计文档 **§4.6 v1.1 完整契约**定义 `SolveXEvent`（含 `stage` / `barrier` / `thinking` / `output` / `turn` / `usage` / `model` / `lifecycle`）、`StageNode`、`RunSummary`（含 `models[]`、`usageByTask`、`issues[]`、`elapsedMs`）。
**验证**：`npm run typecheck`。

### T0.4 配置目录与凭据骨架（v1.1 新增）

**文件**：`packages/pi-runtime/models.json`、`packages/core/src/config/{schema.ts, defaults.ts}`、`docs/adr/0002-webui-2.0.md`

**RED**：`test/config-bootstrap.test.ts` 断言 ① `models.json` 符合 Pi schema（`providers.*.{baseUrl, api, apiKey, models[]}`）；② **不含明文密钥**（`apiKey` 必须为 `$ENV` 形式或缺失）；③ `~/.solvex/config.json` 的 `byPhase` / `defaults` / `thinkingLevel` 结构可解析；④ `concurrency` 默认 3、`strict` 默认 false。
**GREEN**：写最小可用配置（默认 provider 留空，由凭据探测决定）。
**验证**：`npm test -- config-bootstrap`。

> **CP0 检查点**：`npm run check` 全绿；提交 `chore: bootstrap pi-sdk migration workspace (v1.1 contracts)`。

---

## 阶段 1：提示词资产迁移（★ 最高优先级，先做完再碰编排）

> 原则：**逐字搬运**。除设计文档 §5.1 的 R-1/R-2/R-3 白名单替换外，任何改写都视为缺陷。

### T1.1 建立 legacy 基准

**文件**：`docs/legacy-prompts/*`（把 `/tmp` 下载的 10 个 `app/prompt/*.py` 与 `solvex_flow.py` 内联 5 段原文存档）

**RED**：`test/prompts/legacy-baseline.test.ts` 读取 `docs/legacy-prompts/modeling.py`，断言能提取出 `SYSTEM_PROMPT` / `NEXT_STEP_PROMPT` / `REVIEW_PROMPT` 三个常量的原文长度（87/8/34 行等价）。
**GREEN**：写入归档文件 + 提取脚本 `scripts/extract-legacy-prompts.ts`。
**验证**：`npm test -- legacy-baseline`。

### T1.2 迁移 modeling 提示词

**文件**：`packages/core/src/prompts/modeling.system.md`、`modeling.next.md`、`review.md`

**RED**：`test/prompts/modeling.test.ts`
1. 快照断言 `modeling.system.md` 与 legacy 原文逐字一致（仅允许 R-2 工具名替换）；
2. 断言包含 `## Model N:`（编排解析依赖）；
3. 断言 `review.md` 含 `{model_name}` / `{problem}` / `{model_plan}` / `{results}` / `{review_path}` 五个占位符；
4. 断言 `review.md` 以 `VERIFICATION_RESULT` 双标记结尾。

**GREEN**：逐字搬运；工具名按 R-2 替换（`str_replace_editor`→`write/edit`、`webSearchPrime`→`web_search`、删除 `terminate` 句）。
**验证**：`npm test -- prompts/modeling`。

### T1.3 迁移 programming 提示词

**文件**：`programming.system.md`、`programming.next.md`

**RED**：`test/prompts/programming.test.ts`
1. 逐字快照；
2. 断言包含 6 个固定小节标题（`## Key Numerical Results` / `## Sanity Checks` / `## Model Parameters` / `## Data Files Generated` / `## Figures` / `## Issues or Limitations`）；
3. 断言包含 `VERIFICATION_RESULT: SATISFIED` 与 `NEEDS_REVISION`；
4. 断言包含 `matplotlib.use('Agg')` 与 `dpi=300`（图片规范）；
5. 断言 `{output_dir}` 占位符存在。

**GREEN**：搬运 + R-2。
**验证**：`npm test -- prompts/programming`。

### T1.4 迁移 writing 提示词

**文件**：`writing.system.md`、`writing.next.md`

**RED**：`test/prompts/writing.test.ts`
1. 逐字快照；
2. 断言含 7 条 CRITICAL RULES（尤其「USE ONLY the results provided」「INSERT EVERY figure」「CROSS-CHECK numbers」）；
3. 断言含 `WRITE ORDER` 相关语义（在 `inline/paper.ts` 中，见 T1.5）；
4. 断言 LaTeX 图片路径模板 `../02_programming/model_N/figures/` 存在。

**GREEN**：搬运 + R-2。
**验证**：`npm test -- prompts/writing`。

### T1.5 迁移 5 段内联提示词（附录 A，最易漏）

**文件**：`packages/core/src/prompts/inline/{plan,implement,revision,fix,paper}.ts`

**RED**：`test/prompts/inline.test.ts` 逐段断言关键字：

| 文件 | 必须包含 |
| --- | --- |
| `plan.ts` | `PROBLEM:`、`DATA FILES`、`write a multi-model Master Plan`、`'## Model N: Name' section` |
| `implement.ts` | `=== YOUR TASK: Implement`、`MODEL PLAN:`、三个输出路径、`results_summary.md` |
| `revision.ts` | `REVISION`、`PREVIOUS RESULTS` |
| `fix.ts` | `TARGETED REVISION`、`FIX INSTRUCTIONS`、`Fix ONLY the issues above` |
| `paper.ts` | `ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE)`、`AVAILABLE FIGURES (INSERT ALL OF THEM)`、`../02_programming/`、`WRITE ORDER: Write the body sections FIRST, then write the abstract LAST` |

**GREEN**：每个文件导出 `renderX(vars: XVars): string`，变量名与旧 f-string 一致。
**验证**：`npm test -- prompts/inline`。

### T1.6 提示词 ↔ 工具白名单一致性测试（R4 缓解）

**文件**：`test/prompts/tool-consistency.test.ts`、`packages/core/src/prompts/toolNames.ts`

**RED**：正则提取所有 `.md` 中「AVAILABLE TOOLS」段落列出的工具名，断言每个名字都在对应角色的白名单内，且白名单中每个工具都在提示词中被提及（或显式标注为「由系统提供」）。
**GREEN**：建立 `ROLE_TOOLS` 映射（设计文档 §4.5），修正不一致处。
**验证**：`npm test -- tool-consistency`。

### T1.7 归档非主链路提示词

**文件**：`docs/legacy-prompts/{manus,mcp,planning,swe,toolcall,browser,visualization}.md`

**RED**：断言 7 个文件存在且 `prompts/index.ts` **不导出**它们（防止误加载）。
**GREEN**：搬运归档；`visualization` 单独保留到 `prompts/visualization.system.md` 作为可选 stage（P1 优先级）。
**验证**：`npm test -- prompts`。

> **CP1 检查点**：全部提示词快照测试通过；提交 `feat: migrate prompt assets verbatim`。**此检查点之后才允许开始写编排代码。**

---

## 阶段 2：核心编排引擎（零 Pi 依赖，FakeRunner 驱动）

### T2.1 `AgentRunner` 端口 + `FakeAgentRunner`

**文件**：`packages/core/src/ports/{AgentRunner.ts, FakeAgentRunner.ts}`

**RED**：`test/ports/fake-runner.test.ts` 断言 Fake 能按脚本顺序返回 `RunResult`、记录每次 `RunRequest`、支持 `AbortSignal`。
**GREEN**：实现设计文档 §4.3 的接口；Fake 从 `Map<role, RunResult[]>` 取值，并把预置产物写到 `cwd`（模拟 agent 落盘）。
**验证**：`npm test -- ports`。

### T2.2 workspace 模块

**文件**：`packages/core/src/workspace/{index.ts, paths.ts, zip.ts, sessions.ts}`

**RED**：`test/workspace.test.ts`
1. `prepareWorkspace({mode:"create"})` 生成 §2.5 全部目录 + `00_problem/problem.md`；
2. `ingestData()` 支持单文件 / 目录 / zip（zip 内单目录时自动提升）；
3. **关键**：`prepareWorkspace({mode:"resume"})` 预置 `01_modeling/master_plan.md` 后调用，断言文件仍在（E2 回归）；
4. `zipWorkspace()` 产物可被解压还原；
5. `listSessions()` 按创建时间倒序；
6. `modelDirName("Model 1") === "model_1"`。

**GREEN**：TypeScript 重写 `app/workspace.py`，新增 `mode` 参数。
**验证**：`npm test -- workspace`。

### T2.3 Master Plan 解析契约

**文件**：`packages/core/src/contracts/masterPlan.ts`

**RED**：`test/contracts/masterPlan.test.ts`
1. 用 `fixtures/legacy-session/01_modeling/master_plan.md` 解析出 N 个 `Model N`；
2. 无分节时降级 `["Model 1"]`（旧行为）；
3. `sectionFor()` 正确截取到下一个 `## Model` 或 `## Integration` 之前；
4. 分节标题含冒号/特殊字符时正则不炸。

**GREEN**：移植 `_parse_models` / `_extract_model_section` 正则，加 TypeBox 校验。
**验证**：`npm test -- contracts/masterPlan`。

### T2.4 结果契约与 verdict 解析（双轨，ADR-03）

**文件**：`packages/core/src/contracts/{modelResult.ts, verdict.ts, handoff.ts}`、`packages/core/src/gates/parseVerdict.ts`

**RED**：`test/gates/parseVerdict.test.ts`
1. 旧文本 `VERIFICATION_RESULT: SATISFIED` → `{status:"satisfied", source:"legacy"}`；
2. 含 `## Issues Found:` / `## Fix Instructions:` 的 `NEEDS_REVISION` → 正确抽出 `fixInstructions`；
3. 存在 `handoff.json`（TypeBox schema：`{status, issues[], fixInstructions, summaryPath}`）时优先采用，`source:"structured"`；
4. 两者冲突时以 `handoff.json` 为准并记 `warn`；
5. 都缺失 → `{status:"unknown"}` 且触发重试流程（不静默通过）。

**GREEN**：实现双轨解析。
**验证**：`npm test -- gates/parseVerdict`。

### T2.5 质量门 `validateModelOutput`

**文件**：`packages/core/src/gates/validateModelOutput.ts`

**RED**：`test/gates/validateModelOutput.test.ts` 逐个构造缺陷夹具并断言返回对应 `Issue.code`：

| 夹具 | 期望 code |
| --- | --- |
| 无 `results_summary.md` | `MISSING_SUMMARY` |
| 摘要 < 100 字节 | `EMPTY_SUMMARY` |
| 摘要含 `<think/>` | `RAW_THINK_TAGS` |
| 摘要含 "auto-generated" 且无 ⚠ | `AUTOGEN_UNVALIDATED` |
| 无 `.py` | `NO_CODE` |
| CSV `probability` 列和 > 50 且行数 > 10 | `PROBABILITY_SUM_OUT_OF_RANGE` |
| >30% 的 probability > 0.95 | `UNCALIBRATED_PROBABILITIES` |
| `figures/` 不存在或为空 | `NO_FIGURES` |
| 全部正常 | `[]` |

**GREEN**：移植 `_validate_model_output()`，返回结构化 `Issue[]`（`code` / `severity: "critical"|"warn"` / `evidence`），CSV 解析用轻量实现（避免引入 pandas）。
**验证**：`npm test -- gates/validateModelOutput`。

### T2.6 兜底摘要 `ensureSummary`（B2/E4 修复）

**文件**：`packages/core/src/gates/ensureSummary.ts`

**RED**：断言产物**不含** `<think/>`、不含原始工具 JSON、含 `## Status` + `⚠` + `## Sanity Checks` + `## Figures` 结构化小节、且长度 < 2KB。
**GREEN**：只写结构化占位，不塞任何工具输出；同时 `bus.warn(...)`。
**验证**：`npm test -- gates/ensureSummary`。

### T2.7 EventBus

**文件**：`packages/core/src/events/EventBus.ts`

**RED**：断言 `emit` 同步通知订阅者、`history(id)` 可回放、`complete`/`error` 后标记终态、订阅可取消。
**GREEN**：实现（含 `phase` / `model` / `ts` 自动补全）。
**验证**：`npm test -- events`。

### T2.8 四阶段状态机 `SolveXFlow`（★ 核心资产）

**文件**：`packages/core/src/flow/{SolveXFlow.ts, stages.ts, state.ts, resume.ts}`

按 **每个阶段一个任务** 拆：

- **T2.8a** `test/flow/p1-master-plan.test.ts`：断言 P1 调用 modeling runner、产物路径正确；**产物缺失时重试一次**（用更强硬的 `retry` prompt）；两次仍缺 → 抛 `MasterPlanError`。
- **T2.8b** `test/flow/p2-implement.test.ts`：断言按 `parseModels()` 逐个模型调用 programming runner；按 `VERIFICATION_RESULT` 决定是否二次实现（带 `PREVIOUS RESULTS`）；`maxTurns` 传入 30。
- **T2.8c** `test/flow/p2-review.test.ts`：断言每个模型后调用 modeling runner 且 `systemPrompt === review.md`；断言评审 `tools` 为**只读白名单**（A2/F3）；断言 `master_plan.md` 字节前后一致；断言 `NEEDS_REVISION` 时发起定向修复且 prompt 含 `Fix ONLY the issues above`。
- **T2.8d** `test/flow/p2-gate.test.ts`：断言 P2→P3 之间调用 `validateModelOutput()`；`strict` 模式下 Critical Issue 阻断；非 strict 下只 `warn`。
- **T2.8e** `test/flow/p3-aggregate.test.ts`：断言 `all_results_summary.md` 含所有模型的 `results_summary.md` 与图清单。
- **T2.8f** `test/flow/p4-writing.test.ts`：断言 writing runner 收到 Master Plan + 聚合结果 + 图清单 + `WRITE ORDER`；产物 `04_paper/main.tex`。
- **T2.8g** `test/flow/resume.test.ts`：`resumeFrom:2` 跳过 P1 与 model_1；`skipToWriting` 只执行 P4；自动探测首个缺 `results_summary.md` 的模型。
- **T2.8h** `test/flow/events.test.ts`：断言事件序列为 `status(P1) → step → done → ... → complete`，且每个 `done` 前有 `agent_settled` 语义（Fake 模拟）。
- **T2.8i** `test/flow/abort.test.ts`：`AbortSignal` 触发后当前阶段不再发起新调用，状态为 `aborted`，已落盘产物不损坏。

**GREEN**：按设计文档 §4.3 / §5.2 实现。`SolveXFlow` 构造函数只接受 `{runner, bus, workspace, config}`——**不 import 任何 Pi 符号**。
**验证**：`npm test -- flow`（覆盖率 ≥ 85%，状态机分支 100%）。

### T2.9 并行 DAG 调度器（D2 已确认，零 Pi 依赖）

**文件**：`packages/core/src/flow/{scheduler.ts, dag.ts}`、`test/flow/scheduler.test.ts`

**RED**：
1. 用设计文档 §4.4.1 的依赖图构造 5 个模型的 DAG，断言 P1 完成后 `ready()` 一次性返回 5 个 P2-IMPL 任务（**无依赖即并行**）；
2. `concurrency=3` 时同时运行任务数恒 ≤3，其余为 `queued`；
3. 屏障 `barrier(all-results)` 在 5 个模型全部 `done` 前保持 `waiting` 且不派发 P2-REVIEW；全部完成后 `released`；
4. 单任务 `failed` 不取消兄弟任务，屏障处汇总失败项并标记 `completed/total`；
5. `AbortSignal` 触发后不再派发新任务，在跑任务收到取消，已落盘产物不损坏；
6. `concurrency=1` 时 `RunRequest` 顺序与旧版串行 `for` 循环完全一致（golden 断言）；
7. **写安全**：任一任务的 `RunRequest.writablePrefixes` 只含自己的 `02_programming/model_n/`，不含 `all_results_summary.md` / `master_plan.md`（R11）。

**GREEN**：`dag.ts` 用纯函数 `buildDag(models)` + `ready(nodes, done)`；`scheduler.ts` 用带并发上限的 Promise 池 + 屏障计数器，全部经 `AgentRunner` 端口调用（Fake 可跑）。`SolveXFlow` 改为消费 `scheduler` 产出的 `stage` / `barrier` 事件，**仍不 import 任何 Pi 符号**。
**验证**：`npm test -- flow/scheduler`（分支覆盖 100%）。

> **CP2 检查点**：`FakeAgentRunner` 能在 0 次模型调用下跑通完整四阶段（含 `concurrency=1` 与 `concurrency=3` 两种路径）并产出兼容目录；提交 `feat: pi-independent SolveX flow engine + parallel DAG`。

---

## 阶段 3：Pi SDK 适配层

> **此阶段起才允许 import `@earendil-works/pi-coding-agent`。** 每个任务都需要真实 API Key；测试用 `PI_TEST_MODEL` 环境变量指向低成本模型，且标记为 `integration`（CI 默认跳过）。

### T3.1 `models.json` 与配置

**文件**：`packages/pi-runtime/models.json`、`src/config.ts`

**RED**：`test/config.test.ts` 断言默认模型、`byPhase`（P1/P2_IMPL/P2_REVIEW/P3/P4 分档）、`scopedModels`、7 档 `thinkingLevel`、超时默认值可读取，且不含明文密钥。
**GREEN**：按 Pi `models.json` schema 写（设计文档 §3.6）；密钥全部走 `$ENV` 插值或环境变量；`byPhase` 存 `~/.solvex/config.json`。
**验证**：`npm test -- config`。

### T3.2 `PiAgentRunner` 骨架

**文件**：`packages/pi-runtime/src/PiAgentRunner.ts`

**RED**（用 mock 的 `createAgentSession` 做单测，不调真实模型）：
1. 断言按 `role` 取到正确 `systemPromptOverride`；
2. 断言 `appendSystemPromptOverride: () => []` 生效（防止 `APPEND_SYSTEM.md` 污染）；
3. 断言 `tools` 白名单按角色传入；
4. 断言 `sessionManager` 为 `inMemory()`；
5. 断言 `finally` 中 `unsubscribe()` + `dispose()` 必然执行（含抛错路径）；
6. 断言 `AbortSignal` → `session.abort()` + `waitForIdle()`；
7. **v1.1**：断言 `model` / `thinkingLevel` / `scopedModels` / `modelRuntime` 按 `RunRequest` 传入；
8. **v1.1**：断言 `RunRequest.taskId` 透传给 `bridgeEvent()`，事件带正确 `taskId`。

**GREEN**：实现设计文档 §4.3 的 6 步。关键骨架：

```ts
export class PiAgentRunner implements AgentRunner {
  async run(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    const loader = new DefaultResourceLoader({
      cwd: req.cwd,
      agentDir: getAgentDir(),
      systemPromptOverride: () => req.systemPrompt,
      appendSystemPromptOverride: () => [],
      additionalExtensionPaths: [SOLVEX_TOOLS_PATH],
    });
    await loader.reload();

    const { session } = await createAgentSession({
      cwd: req.cwd,
      sessionManager: SessionManager.inMemory(),
      resourceLoader: loader,
      tools: req.tools ?? ROLE_TOOLS[req.role],
      modelRuntime: this.modelRuntime,                       // 单例（T3.6）
      ...(req.model ? { model: req.model } : {}),
      ...(req.thinkingLevel ? { thinkingLevel: req.thinkingLevel } : {}),
      ...(req.scopedModels ? { scopedModels: req.scopedModels } : {}),
    });

    const before = await snapshotFiles(req.cwd);
    let turns = 0;
    const unsubscribe = session.subscribe((event) => {
      if (event.type === "turn_end") turns++;
      bridgeEvent(event, req, this.bus);           // 见 T3.4
      if (req.maxTurns && turns >= req.maxTurns) void session.abort();
    });
    signal?.addEventListener("abort", () => void session.abort(), { once: true });

    try {
      await session.prompt(req.task);
      // 只认 agent_settled；bridgeEvent 内部置 settled 标志
      return {
        text: session.getLastAssistantText(),
        artifacts: await diffFiles(req.cwd, before),
        usage: collectUsage(session),
        settled: true,
      };
    } finally {
      unsubscribe();
      session.dispose();
    }
  }
}
```

**验证**：`npm test -- PiAgentRunner`（mock 版全绿）。

### T3.3 自定义工具扩展 `solvex-tools.ts`

**文件**：`packages/pi-runtime/extensions/solvex-tools.ts`

**RED**：`test/extensions/tools.test.ts` 用 TypeBox 校验参数：
1. `python_execute({code})` 执行 `print(1+1)` 返回 `2`，且**变量不跨调用持久**（第二次调用 `print(x)` 报 NameError）；
2. 超时/非零退出返回 `isError: true` 且带 stderr；
3. `arxiv_search` / `web_search` 参数必填校验生效；
4. `tool_call` 拦截：路径参数含 `..` 逃逸出 `cwd` 时返回 `{block:true, reason}`（R5）。

**GREEN**：

```ts
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "python_execute",
    label: "Run Python",
    description: "Execute Python code in a fresh process. Variables do NOT persist between calls; include imports, computation and print() in one call.",
    parameters: Type.Object({ code: Type.String({ description: "Complete Python snippet" }) }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      const out = await runPython(params.code, { cwd: ctx.cwd, signal, timeoutMs: 120_000 });
      return { content: [{ type: "text", text: out }], details: {} };
    },
  });
  pi.on("tool_call", async (event) => {
    if (hasPathEscape(event.input)) return { block: true, reason: "Path escapes workspace" };
  });
  // arxiv_search / web_search / webReader 同理（或改走 MCP）
}
```

**验证**：`npm test -- extensions`；再跑 `integration: 单阶段 P1 用真实模型生成 master_plan.md`。

### T3.4 事件桥接 `eventBridge.ts`（ADR-09）

**文件**：`packages/pi-runtime/src/eventBridge.ts`

**RED**：`test/eventBridge.test.ts` 用构造的事件对象断言：
1. `text_delta` → `info`（节流 ≥ 100ms 或按 token 聚合）；
2. `tool_execution_start/end` → `step` + `tool`；`isError` → `warn`；
3. `auto_retry_start` / `compaction_start` → `warn`；
4. **`agent_end` 不产生 `done`**；只有 `agent_settled` 才标记阶段结束；
5. `message_end` 覆盖增量拼接的临时文本（附录 C 重建规则）。

**GREEN**：纯函数 `bridgeEvent(event, req, bus)`。
**验证**：`npm test -- eventBridge`。

### T3.5 端到端单阶段集成

**文件**：`test/integration/p1-real.test.ts`（`describe.skipIf(!process.env.PI_TEST_MODEL)`）

**RED→GREEN**：用 `PiAgentRunner` 跑 `tests/simple/linear_programming/problem.md` 的 P1，断言 `01_modeling/master_plan.md` 存在且含 `## Model 1:`。
**验证**：`PI_TEST_MODEL=... npm test -- integration/p1-real`。

### T3.6 模型配置桥接（WebUI 2.0 后端依赖，设计文档 §3.6）

**文件**：`packages/pi-runtime/src/{modelRuntime.ts, config.ts}`

**RED**（mock `ModelRuntime`）：
1. `ModelRuntime.create({authPath, modelsPath})` 只调用一次（**单例**），多阶段 `run()` 复用同一实例；
2. `getAvailable()` 映射为脱敏 `ModelDescriptor[]`（响应体无 `apiKey` 字段）；
3. `byPhase` 配置落到 `RunRequest.model` / `thinkingLevel` / `scopedModels`，未配置时回落 `defaults`；
4. `setRuntimeApiKey()` 的 key **不写文件、不进日志**；
5. thinking 档位按模型能力裁剪（不支持 reasoning → `off`）。

**GREEN**：封装 §3.6 的 API；`PiAgentRunner` 构造函数注入 `modelRuntime`。
**验证**：`npm test -- modelRuntime`。

### T3.7 thinking / turn / usage 事件桥接（ADR-12，设计文档 §4.6）

**文件**：`packages/pi-runtime/src/eventBridge.ts`（扩展 T3.4）

**RED**：在 T3.4 基础上追加：
1. `thinking_start/_delta/_end` → `thinking` 事件，`blockId = taskId + ":" + contentIndex`，`thinking_end` 带权威 `content`；
2. `text_*` / `toolcall_*` → `output` / `tool(delta)`；
3. `turn_start/end` → `turn`；`message_update.usage` → `usage`（`reasoning` **不重复累加**）；
4. `thinking_level_changed` → `model`；`compaction_*` / `auto_retry_*` / `agent_end` → `lifecycle`，**`agent_end` 不产生 `done`**；
5. `message_end` → `output(final)`；
6. `thinking_delta` 节流 ≥60ms；单块 >64KB 截断标记（R12）。

**GREEN**：扩展纯函数 `bridgeEvent(event, req, bus)`，`taskId` 由 `RunRequest` 透传。
**验证**：`npm test -- eventBridge`。

> **CP3 检查点**：真实模型跑通 P1；`npm run check` 全绿；提交 `feat: Pi SDK runtime adapter`。**此处重点核对 R1（实际导出符号与文档一致）、R3（maxTurns 生效）、R4（工具名一致），以及 T3.6/T3.7 与设计文档 §4.6 事件契约逐字段一致。**

---

## 阶段 4：CLI

**文件**：`apps/cli/src/{index.ts, args.ts, renderer.ts}`

| 任务 | RED | GREEN | 验证 |
| --- | --- | --- | --- |
| T4.1 参数解析 | 断言 `-p/-d/-r/--from-model/-w/--session-dir/--strict/--concurrency` 全覆盖且与 §5.3 一致；无参进入交互模式 | 用 `commander` 或手写解析 | `npm test -- cli/args` |
| T4.2 彩色渲染 | 断言 `status/step/done/info/warn` 分别对应旧版 ANSI 输出格式 | 复用旧 `run_flow.py` 的视觉 | `npm test -- cli/renderer` |
| T4.3 `run` 命令 | 用 FakeRunner 断言完整链路被调用、退出码 0/1 正确、超时走 `AbortController` | 组装 core + PiAgentRunner | `npm test -- cli/run` |
| T4.4 `validate` 命令 | 断言对指定 session 重跑质量门且**不修改**任何产物 | 调用 `validateModelOutput` | `npm test -- cli/validate` |
| T4.5 `inspect` 命令 | 断言能读取持久化 session 的阶段列表（用 `SessionManager` / `importFromJsonl`） | 实现 | `npm test -- cli/inspect` |

**CP4**：`solvex run --problem tests/simple/linear_programming/problem.md` 在真实模型下跑通；CLI 帮助文本与旧版参数一一对应。

---

## 阶段 5：WebUI 2.0（★ 本次重点升级，拆 5A 后端 / 5B 前端）

> 设计规格见设计文档 **§10**，事件契约见 **§4.6**。目标：**类 Pi 的模型配置体验 + 思考过程显示 + 运行阶段显示**。前端**整体重写**（不复用旧三件套），旧 4 个端点保持兼容。
> **文件**：`apps/web/src/{server.ts, routes.ts, sse.ts, modelConfig.ts, stages.ts, eventLog.ts}`、`apps/web/public/{index.html, app.js, styles.css, modules/*}`

### 5A 后端：API、SSE、模型配置桥接

| 任务 | RED（supertest / 单测） | GREEN | 验证 |
| --- | --- | --- | --- |
| T5.1 `POST /api/run` | multipart `text`+`files[]` 返回 `{session_id}`；单 zip 解压；空 `text` 400；body 可带 `concurrency`/`strict`/`byPhase` 并透传 `RunRequest` | Fastify + multipart；修旧版 JSON Content-Type bug（Q-Web） | `npm test -- web/run` |
| T5.2 `GET /api/stream/{id}` | 首事件 `status`；`event:`=type、`id:`=自增序号；30s `ping`；`Last-Event-ID` 续传；`complete`/`error` 关流 | `EventBus` → SSE 全事件（§4.6） | `npm test -- web/sse` |
| T5.3 `GET /api/download/{id}` | ZIP 解压后目录与 §2.5 一致 | `zipWorkspace` | `npm test -- web/download` |
| T5.4 `GET /api/sessions` | 倒序、字段 `{id, problem, status, created_at}` 与旧版一致 | `listSessions` | `npm test -- web/sessions` |
| T5.5 `GET /api/artifacts/{id}` | 返回**真实**产物树（旧 `showResults()` 是硬编码假列表） | 扫描 workspace | `npm test -- web/artifacts` |
| T5.6 `POST /api/abort/{id}` | 取消**所有**在跑并行任务，状态 `aborted`，产物不损坏 | `AbortController` → 每个 session `abort()` | `npm test -- web/abort` |
| T5.7 `GET /api/events/{id}?since=N` | 回放 `thinking`/`output`/`tool`/`usage`/`stage` 全类型；`persistThinking:false` 时不含思考正文 | `eventLog.ts` 写 `events.jsonl`（体积上限 + 轮转） | `npm test -- web/events` |
| T5.8 `GET /api/stages/{id}` | 返回完整 `StageNode[]` DAG；并行节点 `state` 独立；屏障含 `completed/total` | `stages.ts` 订阅 `stage`/`barrier` 维护快照 | `npm test -- web/stages` |
| T5.9 `GET /api/models` | 只列 `getAvailable()` 中凭据可用模型；**响应体无明文密钥**，凭据字段均为 `masked`；含 `byPhase`/`thinkingLevels`/`endpoints` | `modelConfig.ts` 封装单例 `ModelRuntime`（T3.6） | `npm test -- web/models` |
| T5.10 `PUT /api/models/config` | 保存默认/分档/scopedModels/thinkingLevel 后 `GET` 回读一致；非法档位被模型能力过滤 | 写 `~/.solvex/config.json` | `npm test -- web/models-config` |
| T5.11 `POST /api/models/refresh` | 改 `models.json` 后 refresh，新端点模型出现在列表 | 重建 catalog / 重载 `models.json` | `npm test -- web/models-refresh` |
| T5.12 `POST /api/models/api-key` | 注入后该 provider 变 `available`；断言 key **不落盘、不进日志** | `setRuntimeApiKey()`（只内存） | `npm test -- web/models-apikey` |
| T5.13 `PUT /api/models/endpoints` | 写入 `baseUrl/api/apiKey($ENV)/models[]`；`$ENV` 插值生效 | 写 `models.json` | `npm test -- web/models-endpoints` |
| T5.14 `GET /api/models/thinking-levels?model=` | 返回该模型支持的档位子集；不支持 reasoning 时返回 `["off"]` | 按模型能力裁剪 | `npm test -- web/thinking-levels` |

> **CP5A**：14 个端点与 SSE 全事件测试全绿；`GET /api/models` 响应体快照断言无任何明文密钥。

### 5B 前端：三视图 + store

**技术选型**：默认**无构建链**——原生 ES modules，`public/{index.html, app.js, styles.css}` + `modules/{store, stream, models, thinking, stages, artifacts}.js`；单一 `SessionStore`，SSE 事件经纯函数 `reduce(event)` 更新，便于不依赖 DOM 做 TDD。

| 任务 | RED（`test/web/*.test.ts`，纯函数） | GREEN | 验证 |
| --- | --- | --- | --- |
| T5.15 `modules/store.js` | 构造 `SolveXEvent` 序列，断言 reducer 正确维护 `stages`/`tasks`/`usage`；`thinking_delta` 拼接结果 == `thinking_end.content`；`message_end` 覆盖 partial；`agent_end` 不把阶段标为 done | `reduce(event)` 纯函数 | `npm test -- web/store` |
| T5.16 `modules/stream.js` | `Last-Event-ID` 断线续传；先拉 `/api/events`+`/api/stages` 再接 SSE；`ping` 不进 store | EventSource 封装 | `npm test -- web/stream` |
| T5.17 `modules/models.js` | 模型选择器按 provider 分组 / 搜索 / 能力标签；设为默认 / 分配到阶段 / 加入循环集；`masked` 展示；thinking 档位按模型过滤 | 模型配置中心抽屉 | `npm test -- web/models-ui` |
| T5.18 `modules/thinking.js` | 思考块默认折叠可展开；按 `contentIndex` 追加；`redacted` 降级；单块 >64KB 截断标记 | 思考过程视图 | `npm test -- web/thinking-ui` |
| T5.19 `modules/stages.js` | 右栏 DAG 时间线：并行节点独立刷新、屏障 `3/5`、失败标红、展开可见 turn/工具/思考/输出 | 运行阶段视图 | `npm test -- web/stages-ui` |
| T5.20 `modules/artifacts.js` + 顶部条 | 真实文件树 + 预览 + ZIP；顶部实时显示模型/thinking/token/¥；`startRun()` 用 `FormData`（不设 JSON Content-Type） | 产物视图 + 状态条 | `npm test -- web/artifacts-ui` |
| T5.21 浏览器冒烟 | — | — | playwright：提交含 CSV 上传 → 观察思考流 → 观察 3 路并行阶段 → 刷新回放 → 下载 ZIP |

> **CP5B**：`solvex serve --port 8000`，浏览器完成一次含文件上传的运行：模型配置中心可切模型与 thinking 档 → 思考过程流式可见 → 右栏显示并行阶段 → 刷新后思考与阶段均可回放 → 下载 ZIP。**对照设计文档 §8 F-8~F-13 逐条签字。**

---

## 阶段 6：质量门与 23 问题回归

按设计文档 §8.2 逐条写成测试（每条一个任务 T6.1–T6.11），全部放在 `test/regression/`：

| 任务 | 对应问题 | 实现方式 |
| --- | --- | --- |
| T6.1 | A2 / F3 | 断言评审 `RunRequest.tools` 为只读；前后 master_plan 字节一致 |
| T6.2 | B2 / E4 | `ensureSummary` 产物无 `<think/>`、无原始 JSON、带 ⚠ |
| T6.3 | B4 / C2 | CSV 夹具触发 `PROBABILITY_SUM_OUT_OF_RANGE` / `UNCALIBRATED_PROBABILITIES` 且发 `warn` |
| T6.4 | B5 | `ModelResult` schema 校验 100% 通过；缺小节触发定向修复 |
| T6.5 | C1 | 评审阶段结束断言 `*_review.md` 存在且含合法 `Verdict` |
| T6.6 | D1 / D4 | 提示词快照含「USE ONLY the results provided」；论文数值与 `all_results_summary.md` 抽样一致性检查 |
| T6.7 | D3 | 提示词快照含 `WRITE ORDER: ... abstract LAST` |
| T6.8 | E1 | 每阶段独立 `timeoutMs`；断言不存在全局 3600s 硬杀 |
| T6.9 | E2 | `prepareWorkspace({mode:"resume"})` 不删除产物 |
| T6.10 | E3 | P2→P3 强制质量门；`--strict` 阻断进入 P4 |
| T6.11 | F1 / F2 | 长文夹具（模拟 80K）+ 阶段隔离会话；断言 compaction 后仍产出完整 `main.tex` |

**额外 T6.12**：`handoff.json` 双轨兼容——用 `fixtures/legacy-session/`（纯旧标记、无 handoff）跑完整流程，断言结果一致（R8）。

**v1.1 追加**：

| 任务 | 对应 | 实现方式 |
| --- | --- | --- |
| T6.13 | R11 并行写安全 | 断言无任何 LLM 会话写 `all_results_summary.md` / `master_plan.md`；越界写入被 `tool_call` 拦截；`all_results_summary.md` 只由 P3 生成；`concurrency=3` 与 `=1` 产物逐字节一致 |
| T6.14 | ADR-12 事件契约 | `thinking_delta` 拼接 == `thinking_end.content`；`message_end` 覆盖 partial；`agent_end` 不产生 `done`；`usage.reasoning` 不重复累加 |

**CP6**：`npm test -- regression` 全绿；输出 `docs/regression-report.md` 逐条对照 23 个旧问题标注「已解决 / 缓解 / 需人工复核」，并附 T6.13/T6.14 结论。

---

## 阶段 7：端到端验收

| 任务 | 内容 | 通过标准 |
| --- | --- | --- |
| T7.1 | 2025 MCM Problem C 精简夹具端到端（`--problem` + `--data`） | 完整产出 4 类产物；目录与旧 session 兼容 |
| T7.2 | 成本/耗时基线 | 记录 `RunSummary` 的 token / cost / elapsedMs；与旧版 ~20 min 对照，写 `docs/benchmark.md` |
| T7.3 | 静态检查 | `grep -r "openai\|anthropic\|requests" packages/core` 无结果；`npm run check` 全绿 |
| T7.4 | 安全审查（R5） | 默认绑定 `127.0.0.1`；路径逃逸拦截测试；文档警示 Pi 非沙箱 |
| T7.5 | 文档 | 更新 README（新 CLI/Web 用法、Node 要求、图片路径修正）、`docs/adr/*`、迁移报告 |
| T7.6 | **Go/No-Go 评审** | 对照 §8 全部验收项逐条签字 |
| T7.7 | **WebUI 2.0 专项验收**（v1.1） | 对照 §8 F-8~F-13：模型配置中心、思考过程、并行阶段视图、刷新回放、用量条、凭据脱敏；playwright 录屏存档 |

---

## 阶段 8：清理与发布

| 任务 | 内容 |
| --- | --- |
| T8.1 | 删除旧 Python 代码（`app/`、`run_flow.py`、`api.py`、`config/`、`requirements.txt`、`setup.py`、`main.py`），仅保留 `docs/legacy-*` 归档与 fixtures |
| T8.2 | 迁移 `docs/superpowers/plans/2026-04-23-solvex-pipeline-issues.md` → `docs/regression-report.md` 后归档 |
| T8.3 | （**D6 已确认不做 `pi-package/`**）改为：归档 `docs/legacy-prompts/`，确认 `packages/core/src/prompts/*.md` 是唯一真源；`solvex inspect <id>` 冒烟；补 `docs/webui-2.0.md` 使用说明 |
| T8.4 | 打 tag、发版、`CHANGELOG.md`；清理 worktree |
| T8.5 | 观察期：保留旧分支 2 周可回滚 |

---

## 回滚策略

| 触发 | 动作 |
| --- | --- |
| 任一 CP 检查点测试不通过 | 停在当前阶段，修复或回退该阶段提交；**不跨检查点继续** |
| 并行调度出问题（R11 / R14） | 设 `concurrency=1` 即刻退回串行语义；DAG / 屏障代码保留但不派发并发，产物契约不变 |
| WebUI 2.0 前端需回退 | 5A 的 API / SSE / 模型配置端点与 5B 前端解耦：可把 `public/` 换回最小 UI 而不动后端；`SolveXEvent` 契约保持兼容 |
| 模型配置体验不达标 | 模型配置全部集中在 `apps/web/src/modelConfig.ts` + `PiAgentRunner` 的 `modelRuntime` 注入点，可单独迭代，不影响编排层 |
| Pi SDK 版本出现 breaking change（R1） | 锁回旧版本；`packages/pi-runtime` 是唯一 import 点，改动不外溢 |
| 端到端质量明显劣于旧版 | 切回 `main` 分支（Python 版保留 2 周）；用 `docs/benchmark.md` 数据定位 |
| 模型供应商不可用 | 切 `models.json` 到备用 provider；golden 回归测试固定模型以隔离变量 |

---

## 完成定义（Definition of Done）

- [ ] §8.1 功能验收 **13 项**全通过（含 F-8~F-13 WebUI 2.0 / 并行）
- [ ] §8.2 质量门 11 项全通过，23 个旧问题逐条有结论
- [ ] §8.3 非功能验收全通过（core 零 SDK 依赖、typecheck/test 绿、覆盖率 ≥85%、提示词快照逐字一致、**并行调度 100% 分支**、**事件契约**、**凭据脱敏**）
- [ ] 提示词资产（10 个 `.py` + 5 段内联）100% 有归档与快照测试
- [ ] CLI 参数与 Web API 与旧版兼容（含 resume / skip-to-writing / `--concurrency`）
- [ ] WebUI 2.0 三能力可演示：模型配置中心、思考过程、运行阶段（§10 / CP5B 录屏）
- [ ] 并行：`concurrency=1` 与串行产物逐字节一致；无 LLM 写共享文件（R11）
- [ ] 仓库中不再存在自研 LLM 调用、Agent Loop、工具集合、上下文压缩代码
- [ ] 不做 `pi-package/`（D6），提示词单一真源已确认
- [ ] README / ADR / 回归报告 / benchmark / WebUI 使用说明齐备
- [ ] Go/No-Go 评审签字

---

## 与 superpowers 工作流的对应

| superpowers 步骤 | 本计划落点 |
| --- | --- |
| 1 头脑风暴 → 规格 | `SolveX-Pi-Migration.md` **v1.1**（§9 决策记录 + §10 WebUI 2.0 规格） |
| 2 隔离工作区 | PRE-4（git worktree `refactor/pi-sdk`） |
| 3 写实施计划 | 本文档（任务 → 文件 → 代码骨架 → 验证命令） |
| 4 子代理驱动 / 执行 | 阶段 1–5B 可按任务派单；5A/5B 可并行派给不同执行者；每任务两段式评审（规格符合度 → 代码质量） |
| 5 TDD | 每个任务显式 RED → GREEN → REFACTOR；测试前代码删除 |
| 6 代码评审 | 每个 CP 检查点做一次对照计划的评审，Critical 阻断 |
| 7 收尾分支 | 阶段 8：验证 → 合并 / 开 PR / 清理 worktree |
| 完成前验证 | T7.3 / T7.6 / 完成定义清单（不靠「看起来修好了」） |
