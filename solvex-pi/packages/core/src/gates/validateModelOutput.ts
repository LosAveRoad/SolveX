import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Issue } from "../events/types.js";

const csvNumber = (s: string) => { const n = Number(s.trim()); return Number.isFinite(n) ? n : null; };

/** 移植 _validate_model_output()，升级为结构化 Issue[]（T2.5）。 */
export function validateModelOutput(modelDir: string): Issue[] {
  const issues: Issue[] = [];
  const summaryPath = join(modelDir, "results_summary.md");

  if (!existsSync(summaryPath)) {
    issues.push({ code: "MISSING_SUMMARY", severity: "critical", evidence: summaryPath });
  } else {
    const size = statSync(summaryPath).size;
    const text = readFileSync(summaryPath, "utf-8");
    if (size < 100) issues.push({ code: "EMPTY_SUMMARY", severity: "critical", evidence: `${size} bytes` });
    if (text.includes("<think/>")) issues.push({ code: "RAW_THINK_TAGS", severity: "critical" });
    if (/auto-generated/i.test(text) && !text.includes("⚠"))
      issues.push({ code: "AUTOGEN_UNVALIDATED", severity: "warn" });
  }

  const files = existsSync(modelDir) ? readdirSync(modelDir) : [];
  if (!files.some((f) => f.endsWith(".py"))) issues.push({ code: "NO_CODE", severity: "critical" });

  for (const f of files.filter((x) => x.toLowerCase().endsWith(".csv"))) {
    const lines = readFileSync(join(modelDir, f), "utf-8").split(/\r?\n/).filter(Boolean);
    if (lines.length < 2) continue;
    const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
    const idx = header.indexOf("probability");
    if (idx < 0) continue;
    const vals = lines.slice(1).map((l) => csvNumber(l.split(",")[idx] ?? "")).filter((v): v is number => v !== null);
    const sum = vals.reduce((a, b) => a + b, 0);
    if (sum > 50 && lines.length - 1 > 10)
      issues.push({ code: "PROBABILITY_SUM_OUT_OF_RANGE", severity: "critical", evidence: `${f}: sum=${sum}` });
    if (vals.length && vals.filter((v) => v > 0.95).length > vals.length * 0.3)
      issues.push({ code: "UNCALIBRATED_PROBABILITIES", severity: "warn", evidence: f });
  }

  const figDir = join(modelDir, "figures");
  if (!existsSync(figDir) || readdirSync(figDir).filter((f) => /\.(png|jpe?g|svg|pdf)$/i.test(f)).length === 0)
    issues.push({ code: "NO_FIGURES", severity: "critical", evidence: "figures/" });

  return issues;
}
