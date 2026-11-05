import { renderTemplate, HANDOFF_HINT } from "./template.js";

const FIX_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}=== Fix {model_name} (TARGETED REVISION) ===\n\nPREVIOUS CODE LOCATION: {abs_model_dir}/\n\n=== FIX INSTRUCTIONS ===\n{fix_section}\n\nFix ONLY the issues above. Save to {abs_model_dir}/\n";

export type FixVars = { input_text: string; data_info: string; model_name: string;
  abs_model_dir: string; fix_section: string };

export function renderFix(v: FixVars): string {
  return renderTemplate(FIX_TEMPLATE, v as unknown as Record<string, unknown>) + HANDOFF_HINT;
}
