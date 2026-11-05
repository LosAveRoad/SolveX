import type { Phase, Role } from "../events/types.js";
import { modelDirName } from "../workspace/paths.js";

export type DagNode = {
  id: string;
  taskId: string;
  label: string;
  phase: Phase;
  kind: "stage" | "task" | "barrier";
  dependsOn: string[];
  model?: string;
  role?: Role;
};

/** §4.4.1 依赖图：只在真实数据依赖处设屏障；无依赖即并行（D2）。 */
export function buildDag(models: string[]): DagNode[] {
  const nodes: DagNode[] = [];
  const push = (n: DagNode) => nodes.push(n);

  push({ id: "P1", taskId: "P1", label: "Phase 1: Master Plan", phase: 1,
         kind: "stage", dependsOn: [], role: "modeling" });
  push({ id: "barrier-master-plan", taskId: "barrier-master-plan", label: "Master Plan ready",
         phase: 1, kind: "barrier", dependsOn: ["P1"] });

  const implIds: string[] = [];
  for (const m of models) {
    const dir = modelDirName(m);
    const id = `P2-IMPL:${dir}`;
    implIds.push(id);
    push({ id, taskId: id, label: `${m}: Implement`, phase: 2, kind: "task",
           dependsOn: ["barrier-master-plan"], model: m, role: "programming" });
  }
  push({ id: "barrier-all-results", taskId: "barrier-all-results", label: "All results + quality gate",
         phase: 2, kind: "barrier", dependsOn: implIds });

  const reviewIds: string[] = [];
  for (const m of models) {
    const dir = modelDirName(m);
    const id = `P2-REVIEW:${dir}`;
    reviewIds.push(id);
    push({ id, taskId: id, label: `${m}: Review`, phase: 2, kind: "task",
           dependsOn: ["barrier-all-results"], model: m, role: "review" });
  }
  push({ id: "barrier-reviews", taskId: "barrier-reviews", label: "All reviews done",
         phase: 2, kind: "barrier", dependsOn: reviewIds });

  push({ id: "P3", taskId: "P3", label: "Phase 3: Aggregate (pure code)", phase: 3,
         kind: "stage", dependsOn: ["barrier-reviews"] });
  push({ id: "P4", taskId: "P4", label: "Phase 4: Paper Writing", phase: 4,
         kind: "stage", dependsOn: ["P3"], role: "writing" });
  return nodes;
}

/** 纯函数：依赖已结算且自身未处理的节点。 */
export function ready<T extends DagNode>(nodes: T[], done: Set<string>, failed: Set<string>,
                                         running: Set<string>): T[] {
  const settled = new Set([...done, ...failed]);
  return nodes.filter((n) => !settled.has(n.id) && !running.has(n.id)
    && n.dependsOn.every((d) => settled.has(d)));
}
