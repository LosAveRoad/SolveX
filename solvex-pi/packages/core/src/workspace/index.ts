import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, statSync, copyFileSync, createReadStream } from "node:fs";
import { join, relative, basename, extname } from "node:path";
import JSZip from "jszip";
import { DIR, META_FILE, modelDirName } from "./paths.js";

export * from "./paths.js";

export type SessionMeta = { id: string; problem: string; status: string; created_at: string; workspaceId?: string };
export type WorkspaceInfo = { id: string; root: string; dir: string;
  paths: { problem: string; data: string; modeling: string; programming: string; paper: string } };

export type PrepareOpts = { root: string; sessionId?: string; mode?: "create" | "resume"; problem?: string };

/** create 建全部目录；resume 只读不删（E2 回归：预置 master_plan.md 不会被清掉）。 */
export function prepareWorkspace(opts: PrepareOpts): WorkspaceInfo {
  const mode = opts.mode ?? "create";
  const id = opts.sessionId ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  const dir = join(opts.root, id);
  const paths = {
    problem: join(dir, DIR.problem), data: join(dir, DIR.data),
    modeling: join(dir, DIR.modeling), programming: join(dir, DIR.programming),
    paper: join(dir, DIR.paper),
  };
  if (mode === "resume" && !existsSync(dir)) throw new Error(`session not found: ${id}`);
  if (mode === "create") {
    for (const p of Object.values(paths)) mkdirSync(p, { recursive: true });
    mkdirSync(join(paths.problem), { recursive: true });
    if (opts.problem !== undefined) writeFileSync(join(paths.problem, "problem.md"), opts.problem);
    const meta: SessionMeta = { id, problem: opts.problem ?? "", status: "running",
      created_at: new Date().toISOString() };
    writeFileSync(join(dir, META_FILE), JSON.stringify(meta, null, 2));
  }
  return { id, root: opts.root, dir, paths };
}

export function writeSessionMeta(ws: WorkspaceInfo, patch: Partial<SessionMeta>): void {
  const f = join(ws.dir, META_FILE);
  const cur: SessionMeta = existsSync(f) ? JSON.parse(readFileSync(f, "utf-8"))
    : { id: ws.id, problem: "", status: "running", created_at: new Date().toISOString() };
  writeFileSync(f, JSON.stringify({ ...cur, ...patch }, null, 2));
}

export function listSessions(root: string): SessionMeta[] {
  if (!existsSync(root)) return [];
  const out: SessionMeta[] = [];
  for (const name of readdirSync(root)) {
    const f = join(root, name, META_FILE);
    if (!existsSync(f)) continue;
    try { out.push(JSON.parse(readFileSync(f, "utf-8"))); } catch { /* skip corrupt meta */ }
  }
  return out.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/** CLI --data 与 Web files[] 共用：单文件 / 目录 / zip 自动解压（zip 内单目录自动提升）。 */
export async function ingestData(ws: WorkspaceInfo, sources: string[]): Promise<string[]> {
  const dest = ws.paths.data;
  mkdirSync(dest, { recursive: true });
  const written: string[] = [];
  for (const src of sources) {
    if (!existsSync(src)) continue;
    const st = statSync(src);
    if (st.isDirectory()) {
      for (const f of walk(src)) {
        const rel = relative(src, f);
        const out = join(dest, basename(src), rel);
        mkdirSync(out.slice(0, out.lastIndexOf("/")), { recursive: true });
        copyFileSync(f, out);
        written.push(relative(ws.dir, out));
      }
    } else if (extname(src).toLowerCase() === ".zip") {
      const zip = await JSZip.loadAsync(readFileSync(src));
      const names = Object.keys(zip.files).filter((n) => !zip.files[n].dir);
      const top = new Set(names.map((n) => n.split("/")[0]));
      const strip = top.size === 1 && names.every((n) => n.includes("/"));
      for (const name of names) {
        const rel = strip ? name.slice(name.indexOf("/") + 1) : name;
        if (!rel || rel.includes("..")) continue;
        const out = join(dest, rel);
        mkdirSync(out.slice(0, out.lastIndexOf("/")), { recursive: true });
        writeFileSync(out, await zip.files[name].async("nodebuffer"));
        written.push(relative(ws.dir, out));
      }
    } else {
      const out = join(dest, basename(src));
      copyFileSync(src, out);
      written.push(relative(ws.dir, out));
    }
  }
  return written;
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  }).filter((p) => !p.includes("__pycache__") && !basename(p).startsWith("."));
}

export async function zipWorkspace(ws: WorkspaceInfo): Promise<Buffer> {
  const zip = new JSZip();
  for (const f of walk(ws.dir)) {
    zip.file(relative(ws.dir, f).split("\\").join("/"), readFileSync(f));
  }
  return zip.generateAsync({ type: "nodebuffer" });
}

export async function unzipWorkspace(buf: Buffer, dest: string): Promise<string[]> {
  const zip = await JSZip.loadAsync(buf);
  const out: string[] = [];
  for (const [name, entry] of Object.entries(zip.files)) {
    if (entry.dir || name.includes("..")) continue;
    const p = join(dest, name);
    mkdirSync(p.slice(0, p.lastIndexOf("/")), { recursive: true });
    writeFileSync(p, await entry.async("nodebuffer"));
    out.push(name);
  }
  return out;
}

export function scanArtifacts(ws: WorkspaceInfo): { path: string; size: number; isDir: boolean }[] {
  if (!existsSync(ws.dir)) return [];
  const out: { path: string; size: number; isDir: boolean }[] = [];
  const visit = (d: string) => {
    for (const n of readdirSync(d)) {
      if (n === META_FILE || n === "events.jsonl") continue;
      const p = join(d, n);
      const isDir = statSync(p).isDirectory();
      out.push({ path: relative(ws.dir, p).split("\\").join("/"), size: isDir ? 0 : statSync(p).size, isDir });
      if (isDir) visit(p);
    }
  };
  visit(ws.dir);
  return out.sort((a, b) => a.path.localeCompare(b.path));
}
