import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const IMAGE_RE = /\.(png|jpe?g|svg|pdf)$/i;
const DATA_RE = /\.(csv|tsv|json|pkl|parquet)$/i;
const CODE_RE = /\.(py|m|r|js|ts)$/i;
const fmt = (n: number) => Number(n.toPrecision(4)).toString();

function walk(dir: string, base = ""): string[] {
  const out: string[] = [];
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const rel = base ? `${base}/${ent.name}` : ent.name;
    if (ent.isDirectory()) out.push(...walk(join(dir, ent.name), rel));
    else if (ent.isFile()) out.push(rel);
  }
  return out;
}

/** 从 CSV 抽取表头、行数与数值列的 min/mean/max，供下游阶段直接引用真实数字。 */
function csvDigest(abs: string): string {
  try {
    const lines = readFileSync(abs, "utf-8").split(/\r?\n/).filter(Boolean);
    if (!lines.length) return "empty file";
    const header = lines[0].split(",").map((h) => h.trim());
    const rows = lines.slice(1);
    const stats: string[] = [];
    for (let i = 0; i < header.length && stats.length < 6; i++) {
      const vals = rows
        .map((r) => Number((r.split(",")[i] ?? "").trim()))
        .filter((v) => Number.isFinite(v));
      if (vals.length < Math.max(2, rows.length * 0.5)) continue;
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
      stats.push(`${header[i]}: n=${vals.length} min=${fmt(Math.min(...vals))} ` +
        `mean=${fmt(mean)} max=${fmt(Math.max(...vals))}`);
    }
    return `columns=${header.length}, data_rows=${rows.length}\n` +
      `  header: ${header.slice(0, 14).join(", ")}\n` +
      (stats.length ? `  numeric: ${stats.join(" | ")}` : "  numeric: (none detected)");
  } catch (e) {
    return `unreadable: ${String(e)}`;
  }
}

/**
 * 纯代码扫描模型目录，把真实产物变成可引用的文本证据（ADR-0009）。
 *
 * 此前 ensureSummary/aggregate 只认 results_summary.md，模型写了 CSV 却没写摘要时，
 * 数千行真实数值会被一句 "⚠ Not available." 完全盖掉。这里不依赖 LLM、不写文件，
 * 只返回文本，供兜底摘要与 all_results_summary.md 使用。
 */
export function summarizeArtifacts(modelDir: string): string {
  if (!existsSync(modelDir)) return "No artifacts directory found.";
  let files: string[];
  try { files = walk(modelDir).sort(); } catch (e) { return `Scan failed: ${String(e)}`; }
  const relevant = files.filter((f) =>
    !/(^|\/)results_summary\.md$/.test(f) && (IMAGE_RE.test(f) || DATA_RE.test(f) || CODE_RE.test(f)));
  if (!relevant.length) return "No data, code or image artifacts found in this model directory.";

  const lines: string[] = ["### Artifacts discovered by SolveX (read-only scan)", ""];
  for (const rel of relevant) {
    const abs = join(modelDir, rel);
    let size = 0;
    try { size = statSync(abs).size; } catch { /* ignore */ }
    lines.push(`- \`${rel}\` (${size} B)`);
    if (/\.csv$/i.test(rel)) {
      for (const l of csvDigest(abs).split("\n")) lines.push(`  ${l}`);
    }
  }
  return lines.join("\n");
}

/** 供测试与运行时快速判断：目录里是否存在任何可用的数据或图片产物。 */
export function hasRealArtifacts(modelDir: string): boolean {
  if (!existsSync(modelDir)) return false;
  try {
    return walk(modelDir).some((f) => DATA_RE.test(f) || IMAGE_RE.test(f));
  } catch { return false; }
}
