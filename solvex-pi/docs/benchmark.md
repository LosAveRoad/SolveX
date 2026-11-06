# 性能与成本基线（benchmark）

> 测量日期：2026-11-05 · 环境：Node 22.20.0 / pnpm 10.28.2 / Pi SDK 1.5.0 · 历史内部测试模式
>
> 注：本页记录 2.0.2 及更早版本的内部测试 runner 实测，仅反映编排层开销；演示模式自 2.0.3 起不再对外提供，这些数字不能代表真实模型成本。

## 本次实测（FakeRunner + 合成 Pi 事件，端到端经 HTTP）

| 指标 | 数值 |
| --- | --- |
| 完整四阶段运行耗时 | **0.025s**（不含真实模型推理） |
| 并行度 | 3（3 个模型 P2-IMPL 并行） |
| SSE 事件总数 | **216** |
| 事件类型覆盖 | 15 类：`status/info/stage/step/lifecycle/model/turn/thinking/output/tool/usage/done/barrier/complete` |
| 其中 thinking / stage / usage / barrier | 40 / 20 / 8 / 6 |
| 阶段 DAG 节点 | 11 |
| 产物文件 | 34（含上传的 `data/data.csv`） |
| 会话凭据脱敏 | 通过（响应体无 `sk-`） |

事件类型分布：`{"status": 6, "info": 3, "stage": 20, "step": 8, "lifecycle": 48, "model": 16, "turn": 16, "thinking": 40, "output": 16, "tool": 16, "usage": 8, "done": 12, "barrier": 6, "complete": 1}`

## 与旧版对照（设计文档 §2.7 / 计划 T7.2）

| 维度 | 旧 Python 版 | 新 TS + Pi 版 |
| --- | --- | --- |
| 端到端耗时 | 约 20 min（2025 MCM Problem C，含真实模型） | **待 PRE-3 凭据补齐后测** |
| 并行 | 串行 `for` 循环 | 无依赖即并行（`concurrency=3`，`=1` 等价旧版） |
| 上下文压缩 | 自研 `compact.py`，F1/F2 缺陷 | Pi 内置 compaction + 一阶段一 session |
| 阶段可观测 | 仅日志文本 | 12 类结构化事件 + DAG 快照 + 用量条 |
| 成本可观测 | 无 | `usage` 按任务与全局两级汇总 |

## 待补充（阻塞于 PRE-3：至少一个可用模型凭据）

- `PI_TEST_MODEL=<provider/id>` 跑 `test/pi/integration.test.ts`（真实模型 P1）。
- 2025 MCM Problem C 夹具端到端（T7.1），记录 `RunSummary` 的 token / cost / elapsedMs。
- 并行 `concurrency=1/3` 的真实耗时与成本对比，验证 R14 成本护栏。

> 说明：fake 模式的耗时仅反映编排层开销，**不可与旧版 20 min 直接比较**；真实成本基线必须在凭据就绪后补测后才能作为 Go/No-Go 依据。
