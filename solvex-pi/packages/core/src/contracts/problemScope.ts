/** 题面按阶段生效（基准 r0 实测：P1 专用的「先写 master_plan、写完即停」被原样注入 P2/P4，
 *  诱发 4 次越界写）。用户可以把只对某些阶段生效的段落包在标记里：
 *
 *    <!-- solvex:phase P1 -->
 *    - Your FIRST tool call MUST be `write` to create 01_modeling/master_plan.md.
 *    <!-- /solvex:phase -->
 *
 *  标记可以列多个阶段（`P1,P4`）。不在列表里的阶段看不到这段；标记本身总是去掉。 */
export type ProblemPhase = "P1" | "P2" | "P3" | "P4";

const BLOCK = /<!--\s*solvex:phase\s+([A-Za-z0-9,\s]+?)\s*-->\n?([\s\S]*?)<!--\s*\/solvex:phase\s*-->\n?/g;

/** 下游阶段追加的说明：题面里没打标记的流程指令同样不该在下游重复执行。 */
export const DOWNSTREAM_PROBLEM_NOTE =
  "\n\n[SolveX] The problem statement above is shared by every phase. Process instructions in it that " +
  "address the planning phase (for example which file to write first, or to stop once the plan is " +
  "written) were already carried out in Phase 1. Follow the task instructions below instead.\n";

export function scopeProblem(problem: string, phase: ProblemPhase): string {
  const scoped = problem.replace(BLOCK, (_m, phases: string, body: string) =>
    phases.split(/[\s,]+/).map((p) => p.trim().toUpperCase()).includes(phase) ? body : "");
  return phase === "P1" ? scoped : scoped + DOWNSTREAM_PROBLEM_NOTE;
}
