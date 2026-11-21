import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderTemplate, PLANNING_POLICY, WORKSPACE_DISCOVERY_POLICY } from "./inline/template.js";
import { TOOL_LIST_PLACEHOLDER } from "./toolCatalog.js";
import { SCRATCH_DIR } from "../workspace/paths.js";

const here = (f: string) => fileURLToPath(new URL(f, import.meta.url));
const load = (f: string) => readFileSync(here(f), "utf-8");

/** 资产逐字保留，仅 P1 在运行时追加执行策略（ADR-0008 / ADR-0014）。 */
export const modelingSystem = () => load("modeling.system.md") + PLANNING_POLICY;
export const modelingNext = () => load("modeling.next.md");
export const programmingSystem = () => load("programming.system.md");
export const programmingNext = (vars: { output_dir: string }) =>
  renderTemplate(load("programming.next.md"), vars);
/** ADR-0009：写作角色可以（且被要求）自行检索共享工作区里的真实产物。 */
export const writingSystem = () => load("writing.system.md") + WORKSPACE_DISCOVERY_POLICY;
export const writingNext = () => load("writing.next.md");
export const visualizationSystem = () => load("visualization.system.md");
export const visualizationNext = () => load("visualization.next.md");

/** 评审会话的 system prompt。此前评审把整段 renderReview 同时当 system prompt 和 task 发送，
 *  题面、计划、结果摘要在每次请求里重复一遍。旧版同样是「角色 system + 评审 prompt 作为任务」。 */
export const reviewSystem = () => REVIEW_SYSTEM;
export const REVIEW_SYSTEM =
  "You are the cross-review agent of a mathematical-modeling pipeline. Another agent implemented one model " +
  "of the Master Plan; your job is to judge whether its results are sound. The task message contains the " +
  "problem, that model's plan section and the programmer's results report. Verify the report against the " +
  "actual code, data files, results.json and figures in the workspace (02_programming/<model>/) before you " +
  "accept a number — run code to recompute numbers when that is the fastest way to check them.\n" +
  "You may run code, but you must not change the implementation: write scratch files only under " +
  `${SCRATCH_DIR}/. Any other file you create or modify is reverted automatically after the review.\n\n` +
  TOOL_LIST_PLACEHOLDER + "\n";

export type ReviewVars = { model_name: string; problem: string; model_plan: string;
                           results: string; review_path: string };
/** REVIEW_PROMPT 的 5 个占位符，变量名与旧 .format() 完全一致（R-1）。 */
export function renderReview(v: ReviewVars): string {
  return renderTemplate(load("review.md"), v as unknown as Record<string, unknown>) + REVIEW_OUTPUT_POLICY;
}

/** 评审可以跑代码核对数字（ADR-0014），但不能改实现：除草稿目录外的改动都会被还原。
 *  逐字资产 review.md 里「不写也不跑代码」「把评审写到 review_path」两句由这段运行时说明覆盖。 */
export const REVIEW_OUTPUT_POLICY = `

RUNTIME NOTE (SolveX — overrides the instructions above where they differ): You MAY run code to verify the
results — for example re-run run.py, or recompute key numbers from the shared dataset and the model's outputs.
Write scratch files only under ${SCRATCH_DIR}/; any other change is reverted automatically after the review, so do
not fix the implementation yourself. Do NOT try to save the review file. When you are done, call the
\`submit_review\` tool with your verdict (SATISFIED or NEEDS_REVISION) and the complete written review — what you
checked and the evidence, plus ## Issues Found: and ## Fix Instructions: when revision is needed. SolveX saves that
\`review\` argument to the review path verbatim; your reply text is not saved. The call is the only way to finish:
if it rejects your submission, fix what it lists and call it again.`;

export * from "./inline/plan.js";
export * from "./inline/implement.js";
export * from "./inline/revision.js";
export * from "./inline/fix.js";
export * from "./inline/paper.js";
export * from "./toolNames.js";
export * from "./toolCatalog.js";
export {
  HANDOFF_HINT, PLANNING_POLICY, RESULTS_CONTRACT, WORKSPACE_DISCOVERY_POLICY, sharedDataNote,
  renderTemplate,
} from "./inline/template.js";
