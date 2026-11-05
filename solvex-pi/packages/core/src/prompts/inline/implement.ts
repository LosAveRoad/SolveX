import { renderTemplate, HANDOFF_HINT, RESULTS_CONTRACT } from "./template.js";

const IMPLEMENT_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}=== YOUR TASK: Implement {model_name} ===\n\nMODEL PLAN:\n{model_plan_section}\n\nSave ALL outputs to:\n  - Code files: {abs_model_dir}/\n  - Figures: {abs_model_dir}/figures/\n  - Results summary: {abs_model_dir}/results_summary.md\n";

/** 摘要缺失时的短会话提示词：只做一件事，把已有产物写成结构化摘要。 */
const SUMMARY_RETRY_TEMPLATE: string =
  "URGENT: {abs_model_dir}/results_summary.md is still missing.\n\n" +
  "The code and data files in that directory already exist — inspect them with ls/read/bash, " +
  "then write results_summary.md NOW using the `write` tool.\n" +
  "Required headings: ## Status, ## Key Numerical Results, ## Sanity Checks, " +
  "## Model Parameters, ## Data Files Generated, ## Figures, ## Issues or Limitations.\n" +
  "Fill 'Key Numerical Results' with the ACTUAL numbers from the CSV files. " +
  "Do not run more experiments. Write the summary and stop.\n";

export type ImplementVars = { input_text: string; data_info: string; model_name: string;
  model_plan_section: string; abs_model_dir: string };

export function renderImplement(v: ImplementVars): string {
  return renderTemplate(IMPLEMENT_TEMPLATE, v as unknown as Record<string, unknown>)
    + HANDOFF_HINT + RESULTS_CONTRACT;
}

export function renderSummaryRetry(v: Pick<ImplementVars, "abs_model_dir">): string {
  return renderTemplate(SUMMARY_RETRY_TEMPLATE, v as unknown as Record<string, unknown>);
}
