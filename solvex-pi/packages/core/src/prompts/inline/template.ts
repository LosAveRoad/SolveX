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
 * P1 运行时执行策略（ADR-0008）。逐字迁移的提示词资产保持不动，只在运行时追加
 * 覆盖说明 —— 沿用 HANDOFF_HINT 的「追加而非改写」模式，T1.2 逐字快照继续成立。
 *
 * 背景：旧 Python 运行时的 arxiv_search / web_search / webReader 在 Pi SDK 1.5.0
 * 中并不存在；逐字提示词里的 "SEARCH (strongly recommended)" 会驱动模型改用
 * bash + curl 模拟联网检索，请求超时后无限重试，永远走不到 WRITE 步骤。
 */
export const OFFLINE_PLAN_POLICY =
  "\n\n=== RUNTIME EXECUTION POLICY (overrides the tool notes above) ===\n" +
  "The legacy search tools arxiv_search, web_search and webReader are NOT registered in this runtime. " +
  "Do NOT call them, and do NOT emulate them with bash, curl, wget, pip install or any other network access: " +
  "network requests are unavailable here and will time out.\n" +
  "The `write` tool IS registered. Use it as your FIRST action to create the deliverable at the exact absolute path given in the task prompt. " +
  "Do not explore the filesystem, do not search for the dataset (it is already provided), and do not install packages.\n" +
  "Once the file is written, stop.\n";

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
  "Write results_summary.md as one of your FINAL actions. Do not stop before it exists.\n";

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
