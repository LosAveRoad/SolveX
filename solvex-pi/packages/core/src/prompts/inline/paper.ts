import { renderTemplate } from "./template.js";

const PAPER_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n=== MASTER PLAN ===\n{master_plan_content}\n\n=== ALL RESULTS (USE THESE EXACT NUMBERS — DO NOT FABRICATE) ===\n{all_results_content}\n\n=== AVAILABLE FIGURES (INSERT ALL OF THEM) ===\n{figure_info}\n\nWrite the complete LaTeX paper to {abs_paper_path}\nTarget: 20-30 pages. Use multiple str_replace_editor calls if needed.\nFirst call: create the file with preamble + abstract + introduction + first model section.\nThen: use str_replace to append remaining sections.\n\nFIGURE PATHS: Use relative path from 04_paper/:\n  \\includegraphics[width=0.8\\textwidth]{../02_programming/model_N/figures/figure_name.png}\n  IMPORTANT: NO single quotes inside the path. Just plain path.\n\nCRITICAL:\n- Use ONLY the numbers from ALL RESULTS above. Do NOT invent predictions or parameters.\n- If a result says PARTIALLY SATISFIED or has issues, report that honestly.\n- Insert EVERY figure listed in AVAILABLE FIGURES — do not skip any.\n- Each model section should have: formulation, implementation, actual results, figures.\n\nWRITE ORDER: Write the body sections FIRST, then write the abstract LAST.\nThe abstract must match the conclusions. Do NOT write the abstract first.\n";

export type PaperVars = { input_text: string; master_plan_content: string;
  all_results_content: string; figure_info: string; abs_paper_path: string };

export function renderPaper(v: PaperVars): string {
  return renderTemplate(PAPER_TEMPLATE, v as unknown as Record<string, unknown>);
}
