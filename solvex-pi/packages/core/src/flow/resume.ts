import { existsSync } from "node:fs";
import { join } from "node:path";
import type { WorkspaceInfo } from "../workspace/index.js";
import { modelDirName } from "../workspace/paths.js";

/** 自动探测首个缺 results_summary.md 的模型（旧版行为保留）。 */
export function detectResumeModel(ws: WorkspaceInfo, models: string[]): number {
  for (let i = 0; i < models.length; i++) {
    if (!existsSync(join(ws.paths.programming, modelDirName(models[i]), "results_summary.md"))) return i + 1;
  }
  return models.length + 1;
}

/** 并行下按「已完成 / 失败」状态跳过，而非按序号（D2）。 */
export function completedModels(ws: WorkspaceInfo, models: string[]): Set<string> {
  return new Set(models.filter((m) =>
    existsSync(join(ws.paths.programming, modelDirName(m), "results_summary.md"))));
}
