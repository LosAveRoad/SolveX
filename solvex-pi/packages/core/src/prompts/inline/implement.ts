import { renderTemplate, HANDOFF_HINT } from "./template.js";

const IMPLEMENT_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}=== YOUR TASK: Implement {model_name} ===\n\nMODEL PLAN:\n{model_plan_section}\n\nSave ALL outputs to:\n  - Code files: {abs_model_dir}/\n  - Figures: {abs_model_dir}/figures/\n  - Results summary: {abs_model_dir}/results_summary.md\n";

export type ImplementVars = { input_text: string; data_info: string; model_name: string;
  model_plan_section: string; abs_model_dir: string };

export function renderImplement(v: ImplementVars): string {
  return renderTemplate(IMPLEMENT_TEMPLATE, v as unknown as Record<string, unknown>) + HANDOFF_HINT;
}
