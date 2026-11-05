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
