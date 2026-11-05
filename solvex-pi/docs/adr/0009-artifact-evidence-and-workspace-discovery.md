# ADR-0009：真实产物证据链与工作区发现

- 状态：Accepted
- 日期：2026-11-05
- 触发：真实模型（DeepSeek）跑 2026 MCM Problem C 后，论文误报「数值计算未完成」

## 现象与证据

四阶段跑完、`error=0`，三个模型目录里确有真实数值产物：

- `model_1/fan_vote_estimates.csv` 2777 行（`pF_med/lo/hi` 可信区间）
- `model_1/weekly_consistency.csv` 336 行（`rhat`/`ess`/`kappa`/`brier`/`spearman`）
- `model_3/couple_weeks_model3.csv` 2777 行，以及 8 个 `.py` 脚本

但论文摘要、Results、Conclusion 都写「数值实验未执行、不编造结果」，且没有任何插图。

## 根因

1. **P2 没写摘要**：`renderImplement` 只给了一行 `Results summary: {path}`，没有强制模板。model_3 跑满 30 turn、7 次 `tool bash failed`，预算耗在调试脚本上，从未调用 `write` 写 `results_summary.md`（事件日志里 16 次提到该文件名全是 `ls`/`head` 查看）。
2. **兜底抹掉证据**：`SolveXFlow` 在 `call()` 返回后检查文件缺失就调 `ensureSummary()`，旧实现无条件写 `⚠ Not available.`。日志 seq 96081 / 140099 有明确 warn。
3. **聚合只读摘要**：`aggregate()` 只读 `results_summary.md`，把 3 份占位符拼成 `all_results_summary.md`（1402 B），完全忽略同目录 CSV。
4. **写作角色无法发现文件**：`ROLE_TOOLS.writing` 只有 `read/write/edit`。P4 实际发起 7 次 `read`，其中 2 次读目录返回 `EISDIR`，其余读到 `master_plan.md` + 3 份占位符摘要 + 自己写的 `main.tex`，**读 CSV 0 次**。`writing.system.md` 又写明「只用 prompt 里的结果」。共享的是文件系统，缺的是目录枚举能力与权威数据源。
5. **图片三重阻塞**：`programming.system.md` 明确要求 matplotlib 出图，但 (a) 运行时 Python 缺 matplotlib；(b) `python_execute` 在旧代码里未注册到 session（ADR-0008 已修）；(c) 一次测试输入里针对 P1 的 OPERATOR 约束被 `input_text` 透传到 P2/P4，含「Do NOT install packages」「Do not run bash」「stop immediately」，与绘图要求直接冲突，导致事件日志里 0 次 `matplotlib`/`savefig`/`pip install`。`NO_FIGURES` 是 critical 但 `strict=false` 放行。

## 决策

1. **放宽写作角色权限**：`ROLE_TOOLS.writing` 增加 `ls/find/grep/bash/python_execute`；review 保持严格只读（A2/F3）。契约校验 `validateRoleTools()` 保证白名单仍是真实工具的子集。
2. **运行时策略按阶段注入**：沿用 `HANDOFF_HINT` / `OFFLINE_PLAN_POLICY` 的「追加不改写」模式，新增 `RESULTS_CONTRACT`（P2）、`WORKSPACE_DISCOVERY_POLICY`（P4）。**运行时约束绝不能塞进 problem 文本**，否则会像本次一样污染所有阶段。逐字提示词资产一字未改。
3. **摘要优先重试**：`renderSummaryRetry()` 在摘要缺失时给一次专门的短会话（对齐 P1 的 `renderPlanRetry`），仍失败才兜底。
4. **兜底摘要必须携带证据**：新增 `summarizeArtifacts(modelDir)` 纯函数，扫描 CSV/代码/图片并提取表头、行数、数值列 min/mean/max；`ensureSummary()` 与 `aggregate()` 都把这份证据写进摘要，`all_results_summary.md` 不再只有占位符。
5. **质量门可观测**：`validateModelOutput` 新增 `PLACEHOLDER_SUMMARY`（critical）。
6. **Python 环境**：运行时需预装 `numpy/pandas/matplotlib`；`checkPythonDeps()` 提供探测，`runPython()` 在 `ModuleNotFoundError` 时返回可执行的安装指引，避免静默跳过绘图。

## 后果

- 即使模型不写摘要，真实 CSV 的数值与文件路径也会进入 `all_results_summary.md`，P4 在 prompt 里就能拿到。
- P4 具备目录枚举能力后被显式授权：遇到占位符必须先 `find`/`ls` 再下结论。
- review 仍只读；逐字资产与 T1.2 / T1.5 快照继续成立。
- 本机已安装 matplotlib 3.11.2；CI 环境需自行声明该依赖，`checkPythonDeps()` 可用于启动自检。
