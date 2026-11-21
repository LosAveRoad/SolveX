/**
 * P4 论文完整性门禁（纯函数）。r6 实测：写作 Agent 写完引言和 Model 1 一节就以空回复结束，
 * 旧门禁只看 main.tex 是否存在，把半篇论文当成交付。这里列出缺失的部分，交给交付物门禁
 * 在同一写作会话里催它接着写。
 */
export const MIN_ABSTRACT_CHARS = 300;

export type PaperGateOpts = { modelCount: number; problem?: string };

/** 题面要求备忘录时才检查/索要（MCM 常见交付物，但不是每道题都有）。 */
export const memoRequired = (problem?: string): boolean => !!problem && /\bmemo(randum)?\b/i.test(problem);

/** 占位符（r6：摘要停在 "PHOLDER"）。只认全大写的标记（r5 正文里有普通单词 "placeholder"），不看 LaTeX 注释。 */
const PLACEHOLDER = /\b(PHOLDER|PLACEHOLDER|TODO|TBD)\b|\b(?:[Ll]orem ipsum)\b/;
const stripComments = (tex: string): string => tex.replace(/(^|[^\\])%.*$/gm, "$1");
export const findPlaceholder = (text: string): string | undefined => ((m) => m?.[1] ?? m?.[0])(PLACEHOLDER.exec(stripComments(text)));

const heading = (tex: string, re: RegExp): boolean =>
  [...tex.matchAll(/\\section\*?\{([^}]*)\}/g)].some((m) => re.test(m[1]));

export function paperGaps(tex: string, opts: PaperGateOpts): string[] {
  const gaps: string[] = [];
  for (let i = 1; i <= opts.modelCount; i++)
    if (!heading(tex, new RegExp(`\\bModel\\s*${i}\\b`, "i")))
      gaps.push(`a \\section for Model ${i} (title containing "Model ${i}")`);
  if (!heading(tex, /conclusion/i)) gaps.push("a \\section{Conclusion}");
  // r6：摘要停留在占位符 "PHOLDER"，正文写完也没回来填。
  const abs = /\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/.exec(tex)?.[1].trim() ?? "";
  if (abs.length < MIN_ABSTRACT_CHARS)
    gaps.push(abs ? `a real abstract (the current one is only "${abs.slice(0, 40)}")` : "an abstract (\\begin{abstract} … \\end{abstract})");
  if (memoRequired(opts.problem) && !heading(tex, /\bmemo(randum)?\b/i))
    gaps.push("the memo required by the problem statement, as its own \\section");
  const ph = findPlaceholder(tex);
  if (ph) gaps.push(`placeholder text "${ph}" replaced with real content`);
  if (!/\\end\{document\}/.test(tex)) gaps.push("\\end{document} (the file is truncated)");
  return gaps;
}
