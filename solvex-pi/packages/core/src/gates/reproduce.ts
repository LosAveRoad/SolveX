import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** 结果契约（ADR-0014）：每个模型目录有入口脚本 run.py，运行后写出 results.json，
 *  results_summary.md 里的数字只能抄自 results.json。 */
export const ENTRY_SCRIPT = "run.py";
export const RESULTS_FILE = "results.json";
export const REPRO_TIMEOUT_MS = 30 * 60_000;

export type ReproResult = { ok: boolean; reason?: string; mismatches?: string[]; ms: number };

/** 把 JSON 展平成 path → 叶子值。 */
function flatten(v: unknown, prefix = "", out: Record<string, unknown> = {}): Record<string, unknown> {
  if (v && typeof v === "object") {
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) flatten(x, prefix ? `${prefix}.${k}` : k, out);
  } else out[prefix] = v;
  return out;
}

const close = (a: unknown, b: unknown) => typeof a === "number" && typeof b === "number"
  ? (Number.isNaN(a) && Number.isNaN(b)) || Math.abs(a - b) <= 1e-9 + 1e-6 * Math.max(Math.abs(a), Math.abs(b))
  : JSON.stringify(a) === JSON.stringify(b);

/** 对比交付的 results.json 与重跑后的结果：缺键、多键、数值不一致都算。 */
export function diffResults(before: unknown, after: unknown): string[] {
  const a = flatten(before), b = flatten(after);
  const out: string[] = [];
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (!(k in b)) out.push(`${k}: delivered ${JSON.stringify(a[k])}, missing after re-run`);
    else if (!(k in a)) out.push(`${k}: not in delivered results.json, re-run produced ${JSON.stringify(b[k])}`);
    else if (!close(a[k], b[k])) out.push(`${k}: delivered ${JSON.stringify(a[k])}, re-run produced ${JSON.stringify(b[k])}`);
  }
  return out;
}

function readJson(path: string): { ok: true; v: unknown } | { ok: false; reason: string } {
  try { return { ok: true, v: JSON.parse(readFileSync(path, "utf-8")) }; }
  catch (e: any) { return { ok: false, reason: `${RESULTS_FILE} is not valid JSON: ${e?.message ?? e}` }; }
}

/**
 * 复现门禁（纯代码，不经过模型）：在模型目录里重跑 `python3 run.py`，确认它能跑通，
 * 并且重新生成的 results.json 与交付的一致。评审最常抓到的问题就是「摘要里的数字在文件里
 * 找不到 / 文件是过期的 / 脚本跑不出交付的结果」（r4、r5）。
 * 异步执行：多个模型并行时不能阻塞事件循环。
 */
export async function reproduce(modelDir: string, opts: { timeoutMs?: number; signal?: AbortSignal } = {}): Promise<ReproResult> {
  const t0 = Date.now();
  const done = (r: Omit<ReproResult, "ms">): ReproResult => ({ ...r, ms: Date.now() - t0 });
  if (!existsSync(join(modelDir, ENTRY_SCRIPT))) return done({ ok: false, reason: `${ENTRY_SCRIPT} is missing` });
  const resultsPath = join(modelDir, RESULTS_FILE);
  if (!existsSync(resultsPath)) return done({ ok: false, reason: `${RESULTS_FILE} is missing` });
  const before = readJson(resultsPath);
  if ("reason" in before) return done({ ok: false, reason: before.reason });

  const run = await new Promise<{ code: number | null; err: string; timedOut: boolean }>((resolve) => {
    const p = spawn("python3", [ENTRY_SCRIPT], { cwd: modelDir, signal: opts.signal,
      env: { ...process.env, MPLBACKEND: "Agg", PYTHONHASHSEED: "0" } });
    let err = "", timedOut = false;
    const timer = setTimeout(() => { timedOut = true; p.kill("SIGKILL"); }, opts.timeoutMs ?? REPRO_TIMEOUT_MS);
    p.stdout.on("data", () => undefined);
    p.stderr.on("data", (d) => { err = (err + String(d)).slice(-4000); });
    p.on("error", (e) => { clearTimeout(timer); resolve({ code: -1, err: String(e), timedOut }); });
    p.on("close", (code) => { clearTimeout(timer); resolve({ code, err, timedOut }); });
  });
  if (run.timedOut) return done({ ok: false, reason: `python3 ${ENTRY_SCRIPT} did not finish within ${Math.round((opts.timeoutMs ?? REPRO_TIMEOUT_MS) / 60000)} min` });
  if (run.code !== 0) return done({ ok: false, reason: `python3 ${ENTRY_SCRIPT} exited with code ${run.code}:\n${run.err.trim().slice(-2000)}` });
  const after = readJson(resultsPath);
  if ("reason" in after) return done({ ok: false, reason: after.reason });
  const mismatches = diffResults((before as { v: unknown }).v, (after as { v: unknown }).v);
  return mismatches.length ? done({ ok: false, reason: "re-running run.py produced different results", mismatches }) : done({ ok: true });
}
