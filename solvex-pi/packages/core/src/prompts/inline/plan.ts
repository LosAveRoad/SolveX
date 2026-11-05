import { renderTemplate, OFFLINE_PLAN_POLICY } from "./template.js";

const PLAN_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}Analyze the problem, search for relevant methods, and write a multi-model Master Plan to {master_plan_path}\nDecide how many specialized models are needed. Each model gets its own '## Model N: Name' section with full math formulation and solution strategy.";

const PLAN_RETRY_TEMPLATE: string = "URGENT: Write a multi-model Master Plan NOW to {master_plan_path}\n\nPROBLEM:\n{input_text}\n\n{data_info}Write the plan immediately with '## Model N:' sections.";

export type PlanVars = { input_text: string; data_info: string; master_plan_path: string };

/** 模板字符串逐字保留；离线执行策略只在运行时追加（ADR-0008）。 */
export function renderPlan(v: PlanVars): string {
  return renderTemplate(PLAN_TEMPLATE, v as unknown as Record<string, unknown>) + OFFLINE_PLAN_POLICY;
}

export function renderPlanRetry(v: PlanVars): string {
  return renderTemplate(PLAN_RETRY_TEMPLATE, v as unknown as Record<string, unknown>) + OFFLINE_PLAN_POLICY;
}
