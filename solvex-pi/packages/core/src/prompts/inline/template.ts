import { SHARED_DATA_DIR } from "../../workspace/paths.js";

/** 内联提示词模板渲染：保留旧 f-string 的 {var} 占位符语义。
 *  \{var} 只匹配简单标识符，LaTeX 的 {\includegraphics...} 不会被误替换。 */
export function renderTemplate(tpl: string, vars: Record<string, unknown>): string {
  return tpl.replace(/\{([a-z_][a-z0-9_]*)\}/gi, (match, key) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : match);
}

/** D3 双轨（§9.1 方案 C）：只追加一句，属增强非改写；handoff.json 优先于文本标记。 */
export const HANDOFF_HINT =
  "\nAlso write a structured handoff.json in your output directory with " +
  "{status, issues, fixInstructions, summaryPath}; the system prefers it over text markers.\n";

/**
 * P1 运行时策略（ADR-0008 / ADR-0011 / ADR-0012 / ADR-0014）。
 *
 * 网络与工具规则沿用 ADR-0008/0011：工具清单由代码发现、以清单为准，不模拟缺失的工具，不联网。
 * ADR-0014 起 P1 不再「先写计划、写完即停、不许看数据」：基准里规划者从没看过数据就定下复现率 ≥0.85、
 * PPC、LOO 这类目标，实现做不到、评审判不通过；各模型又各自解析原始 CSV，重复犯同类数据错误
 * （r3 只用了 335/3,335 行、r5 把 0 分周当成有成绩、标反了规则）。现在 P1 先检查数据、建共享数据集，
 * 再基于它写计划。策略里不出现任何具体工具名。
 */
export const PLANNING_POLICY =
  "\n\n=== PHASE 1 RUNTIME POLICY ===\n" +
  "The AVAILABLE TOOLS section is generated from the tools actually registered in this session; it is authoritative. " +
  "Call only the tools listed there. Never emulate a tool that is absent from that list with shell commands, " +
  "URL fetches, package installs or any other direct network access — such requests are unavailable and will time out.\n" +
  "If a search tool IS listed, you may use it for a bounded literature check (a few calls at most); " +
  "if none is listed, rely on your own knowledge.\n" +
  "You own Phase 1 and have full access to the workspace: you may inspect files, execute code and create files anywhere. Work in three steps, in order:\n" +
  "1. INSPECT THE DATA. The dataset is already in the workspace (see DATA FILES / the data directory); do not search " +
  "elsewhere for it and do not install packages. Load it with code and check columns, row counts, value ranges, " +
  "missing or zero values, the group/season/week structure, and anomalies (withdrawals, ties, annotations inside " +
  "names, duplicated or inconsistently spelled categories, rule changes over time).\n" +
  `2. BUILD THE SHARED DATASET in ${SHARED_DATA_DIR}/: a script prep_data.py that builds it from the raw files; ` +
  "one or more cleaned, analysis-ready CSV tables; data_dictionary.md (every column, units, how special cases are " +
  "encoded, row counts); and checks.md (the validation assertions you ran and their results). Every model in " +
  "Phase 2 will load this dataset as-is and may not modify it, so fix parsing problems here, once.\n" +
  "3. WRITE THE MASTER PLAN at the exact absolute path given in the task. Base every model on the shared dataset, " +
  "name the files it should load, and set validation targets that this data can actually support.\n" +
  "Stop once the shared dataset and the master plan both exist.\n";

/**
 * P2 结果契约（ADR-0009）。逐字模板常量不改，只在 renderImplement 输出末尾追加。
 * 起因：模型把 turn 预算耗在写/调试 Python 脚本上，产出了真实 CSV 却从未写
 * results_summary.md；ensureSummary 随后写占位符，P3/P4 便认为「没有数值结果」。
 */
export const RESULTS_CONTRACT =
  "\n\n=== REQUIRED DELIVERABLES (check before you stop) ===\n" +
  "1. results_summary.md at the exact path above is MANDATORY. Write it with the `write` tool, " +
  "with these six headings, in this order:\n" +
  "   ## Status\n   ## Key Numerical Results\n   ## Sanity Checks\n" +
  "   ## Model Parameters\n   ## Data Files Generated\n   ## Figures\n   ## Issues or Limitations\n" +
  "2. Under 'Key Numerical Results' put the ACTUAL numbers produced by your code " +
  "(estimates, intervals, fit statistics, accuracy). Under 'Data Files Generated' list every " +
  "CSV/JSON file you actually wrote. Never write 'Not available' when data files exist.\n" +
  "3. Generate at least ONE publication-quality figure (matplotlib Agg backend, PNG, dpi>=150) " +
  "into the figures/ subdirectory, and list it under 'Figures'. " +
  "If a plotting dependency is missing, report the exact ImportError instead of skipping silently.\n" +
  "4. If computation genuinely failed, still write the summary with the real error message, " +
  "the files that WERE produced, and an explicit failure status.\n" +
  "5. REPRODUCIBILITY CONTRACT: put an entry script run.py in your output directory. Running `python3 run.py` " +
  "from that directory must regenerate every output (results.json, CSV/JSON files, figures) from the input data, " +
  "deterministically (fix every random seed). run.py must write results.json: one JSON object with every headline " +
  "number (estimates, intervals, fit statistics, validation scores, counts). Every number in results_summary.md " +
  "must be copied from results.json. After you finish, SolveX re-runs run.py and compares results.json; a crash " +
  "or any mismatch is sent back to you to fix.\n" +
  "Write results_summary.md as one of your FINAL actions. Do not stop before it exists.\n";

/** P1 建好共享数据集后追加到 P2 实现提示（ADR-0014）。 */
export const sharedDataNote = (absSharedDir: string): string =>
  "\n\n=== SHARED DATASET (prepared and validated in Phase 1) ===\n" +
  `A cleaned, analysis-ready dataset is in ${absSharedDir}/ — read data_dictionary.md and checks.md there first. ` +
  "Load your data from these tables instead of re-parsing the raw files. The directory is read-only for you: " +
  "do not modify it (changes are reverted). If you find a genuine problem in it, work around it in your own " +
  "code and report it under 'Issues or Limitations'.\n";

/**
 * P4 工作区发现策略（ADR-0009）。writing 角色现在拥有 ls/find/grep/bash/read，
 * 且逐字资产 writing.system.md 写着「只用 prompt 里的结果」。当 ALL RESULTS 是
 * 占位符时，必须显式授权模型自己去共享工作区找真实产物，否则它只会读回那几份
 * 占位符（实测 7 次 read、0 次 CSV、2 次读目录 EISDIR）。
 */
export const WORKSPACE_DISCOVERY_POLICY =
  "\n\n=== WORKSPACE DISCOVERY POLICY (extends the rules above) ===\n" +
  "You now have `ls`, `find`, `grep`, `bash` and `read` in addition to `write`/`edit`. " +
  "The whole session shares one workspace directory (the cwd), so earlier phases' artifacts are visible to you.\n" +
  "IMPORTANT: if the ALL RESULTS section contains placeholders such as " +
  "'Agent did not write results_summary.md', 'not available', or 'No figures generated', " +
  "do NOT conclude that no computation happened. Instead:\n" +
  "  1. Use `find`/`ls` on 02_programming/ to enumerate every CSV, JSON and PNG that actually exists.\n" +
  "  2. Use `read`/`grep` (or `bash` with python) to inspect those files and extract the real numbers.\n" +
  "  3. Build the Results section from those verified numbers and insert the figures you found.\n" +
  "Only report 'results unavailable' after this search confirms there are no data files. " +
  "Reading a directory with `read` returns EISDIR — use `ls`/`find` for directories.\n";
