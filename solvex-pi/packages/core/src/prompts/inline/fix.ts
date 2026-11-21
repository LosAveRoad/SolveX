import { renderTemplate, HANDOFF_HINT } from "./template.js";

const FIX_TEMPLATE: string = "PROBLEM:\n{input_text}\n\n{data_info}=== Fix {model_name} (TARGETED REVISION) ===\n\nPREVIOUS CODE LOCATION: {abs_model_dir}/\n\n=== FIX INSTRUCTIONS ===\n{fix_section}\n\nFix ONLY the issues above. Save to {abs_model_dir}/\n";

export type FixVars = { input_text: string; data_info: string; model_name: string;
  abs_model_dir: string; fix_section: string };

export function renderFix(v: FixVars): string {
  return renderTemplate(FIX_TEMPLATE, v as unknown as Record<string, unknown>) + HANDOFF_HINT;
}

export type ReviewFixVars = { round: number; max_rounds: number; model_name: string;
  abs_model_dir: string; fix_section: string };

/** 评审修复意见直接发进该模型的实现会话（题面、计划、代码与结果都已在会话上下文里），
 *  所以不再重复题面，只给本轮评审的修复意见。上一轮的意见不带：复审是从当前状态重新评审的。 */
export function renderReviewFix(v: ReviewFixVars): string {
  return `=== CROSS-REVIEW ROUND ${v.round}/${v.max_rounds}: Fix ${v.model_name} (TARGETED REVISION) ===\n\n` +
    "An independent reviewer checked your implementation above and asked for revisions.\n\n" +
    `=== FIX INSTRUCTIONS ===\n${v.fix_section}\n\n` +
    `Fix ONLY the issues above. Save to ${v.abs_model_dir}/\n` +
    `Then update ${v.abs_model_dir}/results_summary.md so it reflects the revised code and numbers — ` +
    "the next review reads that file, not your messages.\n" +
    "If after checking you conclude an instruction is wrong, you may leave that part unchanged and say why when you submit.\n" +
    HANDOFF_HINT;
}

/** 复现门禁失败时发回实现会话（ADR-0014）。 */
export function renderReproFix(v: { abs_model_dir: string; detail: string; attempt: number; max_attempts: number }): string {
  return `=== SolveX REPRODUCIBILITY CHECK FAILED (attempt ${v.attempt}/${v.max_attempts}) ===\n\n` +
    `SolveX re-ran \`python3 run.py\` in ${v.abs_model_dir}/ and compared the regenerated results.json with the ` +
    `one you delivered. Result:\n\n${v.detail}\n\n` +
    "Fix run.py (and the code it calls) so that it runs cleanly from that directory and regenerates every output, " +
    "including results.json, deterministically (fix all random seeds). Do not hand-edit results.json. Then make " +
    "results_summary.md match the regenerated results.json. SolveX will re-run the check after you finish.\n";
}
