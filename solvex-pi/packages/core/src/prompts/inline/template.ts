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
 * P1 运行时执行策略（ADR-0008）。逐字迁移的提示词资产（modeling.system.md、
 * PLAN_TEMPLATE）保持不动，只在运行时追加覆盖说明 —— 沿用 HANDOFF_HINT 的
 * 「追加而非改写」模式，T1.2 逐字快照因此继续成立。
 *
 * 背景：旧 Python 运行时的 arxiv_search / web_search / webReader 在 Pi SDK 1.5.0
 * 中并不存在；逐字提示词里的 "SEARCH (strongly recommended)" 会驱动模型改用
 * bash + curl 模拟联网检索，请求超时后无限重试，永远走不到第 5 步 WRITE，
 * 导致 P1 不产出 master_plan.md（实测 13k+ 事件、0 产物）。
 */
export const OFFLINE_PLAN_POLICY =
  "\n\n=== RUNTIME EXECUTION POLICY (overrides the tool notes above) ===\n" +
  "The legacy search tools arxiv_search, web_search and webReader are NOT registered in this runtime. " +
  "Do NOT call them, and do NOT emulate them with bash, curl, wget, pip install or any other network access: " +
  "network requests are unavailable here and will time out.\n" +
  "The `write` tool IS registered. Use it as your FIRST action to create the deliverable at the exact absolute path given in the task prompt. " +
  "Do not explore the filesystem, do not search for the dataset (it is already provided), and do not install packages.\n" +
  "Once the file is written, stop.\n";
