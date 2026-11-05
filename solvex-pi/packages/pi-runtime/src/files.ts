import { existsSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

export function snapshotFiles(cwd: string): Map<string, string> {
  const out = new Map<string, string>();
  if (!existsSync(cwd)) return out;
  const visit = (d: string) => {
    for (const n of readdirSync(d)) {
      if (n === "node_modules" || n === ".git") continue;
      const p = join(d, n);
      const st = statSync(p);
      if (st.isDirectory()) visit(p);
      else out.set(relative(cwd, p).split("\\").join("/"), `${st.size}:${st.mtimeMs}`);
    }
  };
  visit(cwd);
  return out;
}

export function diffFiles(cwd: string, before: Map<string, string>): string[] {
  const after = snapshotFiles(cwd);
  return [...after.keys()].filter((k) => before.get(k) !== after.get(k));
}
