import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderTemplate } from "./inline/template.js";

const here = (f: string) => fileURLToPath(new URL(f, import.meta.url));
const load = (f: string) => readFileSync(here(f), "utf-8");

export const modelingSystem = () => load("modeling.system.md");
export const modelingNext = () => load("modeling.next.md");
export const programmingSystem = () => load("programming.system.md");
export const programmingNext = (vars: { output_dir: string }) =>
  renderTemplate(load("programming.next.md"), vars);
export const writingSystem = () => load("writing.system.md");
export const writingNext = () => load("writing.next.md");
export const visualizationSystem = () => load("visualization.system.md");
export const visualizationNext = () => load("visualization.next.md");

export type ReviewVars = { model_name: string; problem: string; model_plan: string;
                           results: string; review_path: string };
/** REVIEW_PROMPT 的 5 个占位符，变量名与旧 .format() 完全一致（R-1）。 */
export function renderReview(v: ReviewVars): string {
  return renderTemplate(load("review.md"), v as unknown as Record<string, unknown>);
}

export * from "./inline/plan.js";
export * from "./inline/implement.js";
export * from "./inline/revision.js";
export * from "./inline/fix.js";
export * from "./inline/paper.js";
export * from "./toolNames.js";
export { HANDOFF_HINT, renderTemplate } from "./inline/template.js";
