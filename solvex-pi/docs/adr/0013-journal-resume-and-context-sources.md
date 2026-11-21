# ADR-0013：基于会话日志的断点续跑，以及各 Agent 的上下文来源

- 状态：Accepted
- 日期：2026-11-20
- 修订：2026-11-20 同日修订——fork 改为同一会话追加调用；provisional 标注改为最多 3 轮的评审循环
- 关联：ADR-0003（并行 DAG）、ADR-0004（双轨交接）、ADR-0009（产物证据）、`docs/benchmark.md`

## 背景

**续跑**。旧策略靠文件推断：某个模型目录里有 `results_summary.md` 就把它的实现和评审一起跳过。
用 FakeRunner 复现后发现：
1. 部分续跑时，被跳过的模型会从 P3 汇总、P4 图表清单和 `RunSummary` 里消失（模型列表取自
   「本次实际跑过的节点」）；
2. 评审阶段中断后续跑，评审会被整体跳过（实现都有摘要），结论和修复都丢了，系统也不报错；
3. `ensureSummary` 兜底生成的摘要也会被当成「已完成」，失败的模型不再重跑；
4. `--from-model N` 里的 N 只起开关作用，与帮助文本不符；
5. Agent 会话本身是 `SessionManager.inMemory()`，中断的会话只能从头开始。

而 Pi SDK 本身就把会话逐条追加写成 JSONL（每条消息 `appendFileSync`，崩溃不丢），重建上下文时
还会修补孤立的 tool call、跳过出错/中止的 assistant 消息。续跑不需要为每类 Agent 单独写规则。

**上下文**。逐个核对每个 Agent 的输入后发现：评审把整段 prompt 同时当 system prompt 和任务发送（每次
请求重复一遍）；定向修复只拿到评审意见，没有计划片段和上一版结果，r3 里 3/3 修复会话撞上 30 轮上限；
P4 完全看不到评审结论；题面原样注入每个阶段，P1 专用约束泄漏到下游（r0 诱发 4 次越界写）；
摘要补写会话只拿到一个目录路径。

## 决策

### 1. 基于 Pi 会话日志续跑

- `RunRequest.journal = { path, call }`：`path` 是会话日志（`<run>/.solvex/journal/<会话>.jsonl`），
  `call` 是这次调用在会话里的语义名（会话与调用的划分见第 2 节）。名字不用调用序号：重跑时某个兜底调用
  不再触发，后面的调用也不会错位。
- `PiAgentRunner` 用 `SessionManager.open(path)` 打开这份日志，SolveX 只追加两种 custom 条目（不进入
  LLM 上下文）：`solvex_call`（某次调用开始）和 `solvex_result`（该次调用正常结束，含最终回复）。
- 同一 path + call 再次运行时：
  - 有对应的 `solvex_result` → **回放**：直接返回记录的回复和用量，不建会话、不调用模型；
  - 有任务但没有完成标记 → **接着跑**：恢复完整对话，发一条「继续」消息（不重发原任务），
    轮次预算和用量从日志里已有的部分接着算；
  - 撞上限后、写标记前进程退出 → 补记为截断结束，不再调用模型；
  - 取消或出错的调用不写完成标记，下次接着跑；
  - 没开始过 → 写入 `solvex_call` 后在会话末尾发新任务，继承之前的全部上下文。
- **编排层不做任何按节点的跳过**。续跑就是在同一个 run 目录上把流水线从头执行一遍：门禁、汇总都按当前
  文件重新计算，已完成的调用由日志回放。上面第 1、2、3 个问题因此一起消失。`--from-model` 删除，
  `resumeFrom` / `completedModels` / `detectResumeModel` 删除。
- 入口：CLI `run -r <id>`；Web `POST /api/resume/:id`（界面上的「从断点续跑」）。续跑沿用首次运行落盘
  的题面、配置快照和数据说明（`dataInfo` 写入 run 元数据），保证中断前后的 prompt 一致。Web 续跑会先等
  上一次流水线真正停下（abort 后在跑任务收尾），避免两条流水线同写一个目录。

### 2. 一个 Agent 一个会话，后续调用都发进同一个会话

日志按会话划分，会话里每次调用有自己的 call 名（`solvex_call` / `solvex_result` 标记界定范围）：

| 会话（日志文件） | 调用（call） |
|---|---|
| `P1` | `plan`、`plan-retry` |
| `P2-IMPL_model_i` | `impl`、`summary-0`、`revision`、`summary-1`、`fix-1`、`fix-1-summary`、`fix-2`…`fix-3` |
| `P2-REVIEW_model_i.review-r` | `review`（每轮评审一个全新会话） |
| `P4` | `paper` |

摘要补写、自检修订、评审修复意见都**直接发进该模型的实现会话**，不另开修复 Agent：模型看得到计划片段、
自己的代码思路和已算出的结果。修复调用沿用实现节点的 taskId、模型配置与写权限（此前修复用的是评审阶段的
模型配置）。修复提示（`renderReviewFix`）不再重复题面，只给本轮评审的修复意见，并要求更新 results_summary.md。

### 3. 有界评审循环（取代 provisional 标注）

- 每个模型最多评审 `MAX_REVIEW_ROUNDS = 3` 次：评审 → 修复 → 复审 …；某轮 SATISFIED 即止；
  第 3 次修复后直接放行，不再评审。
- 每轮复审都是全新会话、从当前状态重新评审；修复只带本轮意见，上一轮未解决的意见直接丢弃，不累积。
- 每轮评审全文落盘 `*_review_r{n}.md`（`*_review.md` 为最新一轮）；结论只取本轮评审者的输出。
- 复审读的是 results_summary.md：修复后摘要没更新，就在实现会话里补一轮摘要（`fix-n-summary`）。
- P3 汇总与 P4 不再携带评审状态，也不再有 Validated / Provisional 标注。r4 实测：把评审意见交给 P4 后，
  写作 Agent 会自己"纠正"数据并且纠正错（Pareto 两端读法自相矛盾），数据问题应该在代码里修。
  `RunSummary.models[]` 记录最终结论与评审轮数（`reviewRounds`）。
- 其余：评审有独立的 system prompt（评审内容只发一次）；题面按阶段生效（`<!-- solvex:phase P1 -->`）。

## 取舍

- 日志放在 run 目录内的隐藏目录 `.solvex/journal/`，跟着 run 走（拷贝、下载、删除都一致），产物树不展示。
  P4 的写作 Agent 有 `bash`，理论上能 `grep -r` 到日志；目前没有观察到，若出现再加读拦截。
- 后续调用继承实现会话的全部上下文，单次请求的 prompt 变长（大部分命中缓存，超窗由 Pi compaction
  处理），换来不必重新摸索现场。
- 本 ADR 之前创建、没有日志的 run 续跑时会重跑全部 Agent 调用。
- 第 3 次修复后不再复审即放行，论文不会说明哪些评审意见没有解决；换来流程有界、P4 不接触评审内容。

## 验证

- 单测：`test/pi/PiAgentRunner.test.ts`（首次落盘、回放、接着跑且轮次/用量延续、出错不写标记、
  撞上限补记、同一会话多次调用及其中断续跑）、`test/flow/pipeline.test.ts`（评审中断后续跑只重跑中断点之后
  的调用、P3 覆盖全部模型；修复发进实现会话；最多 3 轮评审且只带本轮意见；修复后补摘要；无 provisional；
  评审 system ≠ 任务；题面按阶段生效）、
  `test/web/resume.test.ts`。
- 真实 SDK 冒烟（GLM 5.3 Flash，`bench/smoke/journal-smoke.ts`）：子进程做完 4 步中的 2 步时被 SIGKILL →
  续跑从第 3 步接着做完、未重做前两步；再次运行毫秒级回放；在同一会话追加一次调用，不用工具即可答出之前
  创建的文件和内容；两次调用各自回放。
