import { homedir } from "node:os";
import { join } from "node:path";

export const DIR = {
  problem: "00_problem", data: "data", modeling: "01_modeling",
  programming: "02_programming", paper: "04_paper",
} as const;

export const SESSION_ROOT = join(homedir(), ".solvex", "sessions");
export const META_FILE = ".solvex-meta.json";

/** 与旧 Python 版一致："Model 1" -> "model_1" */
export function modelDirName(modelName: string): string {
  return modelName.toLowerCase().replace(/ /g, "_");
}

export function sessionDir(root: string, id: string): string { return join(root, id); }
export function modelDir(ws: string, modelName: string): string {
  return join(ws, DIR.programming, modelDirName(modelName));
}
