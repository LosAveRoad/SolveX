import { renderTemplate, HANDOFF_HINT } from "./template.js";

const REVISION_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}=== Re-implement {model_name} (REVISION) ===\n\nMODEL PLAN:\n{model_plan_section}\n\nPREVIOUS RESULTS:\n{prev_summary}\n\nFix and save to {abs_model_dir}/\n";

export type RevisionVars = { input_text: string; data_info: string; model_name: string;
  model_plan_section: string; prev_summary: string; abs_model_dir: string };

export function renderRevision(v: RevisionVars): string {
  return renderTemplate(REVISION_TEMPLATE, v as unknown as Record<string, unknown>) + HANDOFF_HINT;
}
