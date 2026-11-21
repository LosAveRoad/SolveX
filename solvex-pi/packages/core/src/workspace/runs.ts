import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { META_FILE, RUNS_DIR } from "./paths.js";
import type { SessionMeta } from "./index.js";

export type RunRoot = { root: string; workspaceId?: string };
export type RunRecord = { id: string; dir: string; root: string;
  workspaceId?: string; meta: SessionMeta };
export type RunIndexOpts = { workspaceRoot?: string; sessionRoot?: string; workspaceId?: string };

const validRunId = (id: string) => /^[A-Za-z0-9_-]+$/.test(id);
const readMetas = (root: string): SessionMeta[] => {
  if (!existsSync(root)) return [];
  const out: SessionMeta[] = [];
  for (const name of readdirSync(root)) {
    const f = join(root, name, META_FILE);
    if (!existsSync(f)) continue;
    try { out.push(JSON.parse(readFileSync(f, "utf-8"))); } catch { /* skip corrupt meta */ }
  }
  return out.sort((a, b) => b.created_at.localeCompare(a.created_at));
};

/**
 * 所有可写的 run 根：新布局 workspaces/{id}/runs/，以及旧版平铺的 sessions/。
 * 旧目录只读兼容，不会被改写或删除。
 */
export function runRoots(workspaceRoot?: string, sessionRoot?: string): RunRoot[] {
  const out: RunRoot[] = [];
  if (sessionRoot) out.push({ root: sessionRoot });
  if (workspaceRoot && existsSync(workspaceRoot)) {
    for (const id of readdirSync(workspaceRoot)) {
      const r = join(workspaceRoot, id, RUNS_DIR);
      if (existsSync(r) && statSync(r).isDirectory()) out.push({ root: r, workspaceId: id });
    }
  }
  return out;
}

/** 跨工作区（含旧 sessions）按创建时间倒序列出 run；可按工作区过滤。 */
export function listAllRuns(opts: RunIndexOpts): RunRecord[] {
  const out: RunRecord[] = [];
  for (const { root, workspaceId: derived } of runRoots(opts.workspaceRoot, opts.sessionRoot)) {
    for (const meta of readMetas(root)) {
      const workspaceId = meta.workspaceId ?? derived;
      if (opts.workspaceId && workspaceId !== opts.workspaceId) continue;
      out.push({ id: meta.id, dir: join(root, meta.id), root, workspaceId, meta });
    }
  }
  return out.sort((a, b) => b.meta.created_at.localeCompare(a.meta.created_at));
}

/** runId → 所在目录根；用于进程重启后的只读回放。 */
export function findRun(id: string, opts: RunIndexOpts): (RunRoot & { dir: string }) | undefined {
  if (!validRunId(id)) return undefined;
  for (const { root, workspaceId } of runRoots(opts.workspaceRoot, opts.sessionRoot)) {
    const dir = join(root, id);
    if (existsSync(join(dir, META_FILE)))
      return { root, dir, workspaceId: readMetas(root).find((m) => m.id === id)?.workspaceId ?? workspaceId };
  }
  return undefined;
}
