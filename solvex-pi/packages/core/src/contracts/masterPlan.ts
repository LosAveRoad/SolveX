/** 移植 solvex_flow.py 的 _parse_models / _extract_model_section 正则（保留降级行为）。 */
export function parseModels(masterPlan: string): string[] {
  const matches = [...masterPlan.matchAll(/## (Model \d+)/g)].map((m) => m[1]);
  return matches.length ? matches : ["Model 1"];
}

function escapeRe(s: string): string { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

export function sectionFor(masterPlan: string, modelName: string): string {
  const pattern = new RegExp(
    `(## ${escapeRe(modelName)}:.*?)(?=\\n## (?:Model \\d+|Integration)|$)`, "s");
  const m = masterPlan.match(pattern);
  return m ? m[1].trim() : masterPlan;
}
