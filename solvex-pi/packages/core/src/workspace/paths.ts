import { homedir } from "node:os";
import { join } from "node:path";

export const DIR = {
  problem: "00_problem", data: "data", modeling: "01_modeling",
  programming: "02_programming", paper: "04_paper",
} as const;

/** P1 产出的共享数据集（清洗后的分析表 + 数据字典 + 校验记录）；P1 之后对所有 Agent 只读。 */
export const SHARED_DATA_DIR = `${DIR.modeling}/shared_data`;
/** 评审跑代码时的草稿目录；评审对其它文件的改动会被自动还原。 */
export const SCRATCH_DIR = ".solvex/scratch";

export const SESSION_ROOT = join(homedir(), ".solvex", "sessions");
export const WORKSPACE_ROOT = join(homedir(), ".solvex", "workspaces");
export const META_FILE = ".solvex-meta.json";

/** 一道题一个工作区；工作区下每次运行一个独立目录，互不覆盖。 */
export const RUNS_DIR = "runs";
export const INPUTS_DIR = "inputs";
export const WORKSPACE_META_FILE = "workspace.json";
export const RUNTIME_FILE = "runtime.json";
/** 每个 Agent 调用一份 Pi 会话日志（JSONL），断点续跑直接基于它（见 SolveXFlow.journal）。 */
export const JOURNAL_DIR = ".solvex/journal";

export function journalPath(wsDir: string, key: string): string {
  return join(wsDir, JOURNAL_DIR, `${key.replace(/[^A-Za-z0-9._-]/g, "_")}.jsonl`);
}

/** 与旧 Python 版一致："Model 1" -> "model_1" */
export function modelDirName(modelName: string): string {
  return modelName.toLowerCase().replace(/ /g, "_");
}

export function sessionDir(root: string, id: string): string { return join(root, id); }
export function modelDir(ws: string, modelName: string): string {
  return join(ws, DIR.programming, modelDirName(modelName));
}

export function workspaceDir(workspaceRoot: string, workspaceId: string): string {
  return join(workspaceRoot, workspaceId);
}
export function runsRoot(workspaceRoot: string, workspaceId: string): string {
  return join(workspaceDir(workspaceRoot, workspaceId), RUNS_DIR);
}
export function runDir(workspaceRoot: string, workspaceId: string, runId: string): string {
  return join(runsRoot(workspaceRoot, workspaceId), runId);
}
