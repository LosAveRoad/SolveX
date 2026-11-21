import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { createHash } from "node:crypto";

/** 字节级文件快照：bash / Python 执行能写任何地方（写拦截只覆盖 write/edit 工具），
 *  所以「只读」只能靠事后还原保证。 */
export type FileSnapshot = { roots: string[]; files: Map<string, Buffer>; paths: Set<string> };

const MAX_BYTES = 64 * 1024 * 1024;   // 单个快照上限，防止把超大数据整个读进内存

function walk(root: string, out: string[]): void {
  if (!existsSync(root)) return;
  if (statSync(root).isFile()) { out.push(root); return; }
  for (const n of readdirSync(root)) {
    if (n === "__pycache__") continue;
    walk(join(root, n), out);
  }
}

export function captureFiles(roots: string[]): FileSnapshot {
  const files = new Map<string, Buffer>(), paths = new Set<string>();
  let total = 0;
  for (const root of roots) {
    const list: string[] = [];
    walk(root, list);
    for (const f of list) {
      paths.add(f);                       // 路径全部记录：超出上限的文件不还原内容，但也绝不当成「新文件」删掉
      const size = statSync(f).size;
      if (total + size > MAX_BYTES) continue;
      total += size;
      files.set(f, readFileSync(f));
    }
  }
  return { roots, files, paths };
}

/** 文件指纹（相对路径 → sha1），只存哈希，可落盘。用于判断一次修复到底改没改文件。 */
export type Fingerprint = Record<string, string>;

export function fingerprint(root: string): Fingerprint {
  const list: string[] = [];
  walk(root, list);
  const out: Fingerprint = {};
  for (const f of list) out[relative(root, f)] = createHash("sha1").update(readFileSync(f)).digest("hex");
  return out;
}

/** 两次指纹之间新增、删除或内容变化的相对路径（排序）。 */
export function changedFiles(before: Fingerprint, after: Fingerprint): string[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys].filter((k) => before[k] !== after[k]).sort();
}

/** 还原快照：改过、删掉的文件恢复原样，快照之后新建的文件删除。返回变动的相对路径。 */
export function restoreFiles(snap: FileSnapshot, base: string): { restored: string[]; removed: string[] } {
  const restored: string[] = [], removed: string[] = [];
  for (const [f, b] of snap.files) {
    if (!existsSync(f) || !readFileSync(f).equals(b)) {
      mkdirSync(dirname(f), { recursive: true });
      writeFileSync(f, b);
      restored.push(relative(base, f));
    }
  }
  for (const root of snap.roots) {
    if (!existsSync(root) || statSync(root).isFile()) continue;
    const now: string[] = [];
    walk(root, now);
    for (const f of now) if (!snap.paths.has(f)) { rmSync(f, { force: true }); removed.push(relative(base, f)); }
  }
  return { restored, removed };
}
