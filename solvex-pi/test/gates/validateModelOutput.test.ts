import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync, unlinkSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { validateModelOutput } from "@solvex/core";

const SUMMARY = `# Results\n\n## Key Numerical Results\n1\n\n## Sanity Checks\nok\n\n## Model Parameters\na\n\n## Data Files Generated\nb\n\n## Figures\nc\n\n## Issues or Limitations\nnone\n`;
function fixture(over: Record<string, string> = {}, extra: Record<string, string> = {}) {
  const d = mkdtempSync(join(tmpdir(), "solvex-gate-"));
  mkdirSync(join(d, "figures"));
  const files: Record<string, string> = { "model.py": "print(1)", "results_summary.md": SUMMARY,
    "figures/fig1.png": "png", ...extra };
  for (const [k, v] of Object.entries({ ...files, ...over })) {
    const p = join(d, k); mkdirSync(p.slice(0, p.lastIndexOf("/")), { recursive: true }); writeFileSync(p, v);
  }
  return d;
}
const codes = (d: string) => validateModelOutput(d).map((i) => i.code);

describe("T2.5 validateModelOutput 结构化质量门", () => {
  it("全部正常 -> []", () => expect(codes(fixture())).toEqual([]));
  it("缺摘要 -> MISSING_SUMMARY", () => {
    const d = fixture(); unlinkSync(join(d, "results_summary.md"));
    expect(codes(d)).toContain("MISSING_SUMMARY");
  });
  it("摘要过短 -> EMPTY_SUMMARY", () => expect(codes(fixture({ "results_summary.md": "x" }))).toContain("EMPTY_SUMMARY"));
  it("含 <think/> -> RAW_THINK_TAGS", () => expect(codes(fixture({ "results_summary.md": SUMMARY + "<think/>" }))).toContain("RAW_THINK_TAGS"));
  it("auto-generated 无 ⚠ -> AUTOGEN_UNVALIDATED", () => expect(codes(fixture({ "results_summary.md": SUMMARY + "auto-generated" }))).toContain("AUTOGEN_UNVALIDATED"));
  it("无 .py -> NO_CODE", () => {
    const d = fixture(); unlinkSync(join(d, "model.py"));
    expect(codes(d)).toContain("NO_CODE");
  });
  it("probability 总和 >50 且行数 >10 -> PROBABILITY_SUM_OUT_OF_RANGE", () => {
    const rows = Array.from({ length: 12 }, (_, i) => `${i},5.0`).join("\n");
    expect(codes(fixture({}, { "p.csv": `id,probability\n${rows}\n` }))).toContain("PROBABILITY_SUM_OUT_OF_RANGE");
  });
  it(">30% probability >0.95 -> UNCALIBRATED_PROBABILITIES", () => {
    const rows = Array.from({ length: 10 }, (_, i) => `${i},0.99`).join("\n");
    expect(codes(fixture({}, { "p.csv": `id,probability\n${rows}\n` }))).toContain("UNCALIBRATED_PROBABILITIES");
  });
  it("无 figures -> NO_FIGURES", () => {
    const d = fixture(); rmSync(join(d, "figures"), { recursive: true });
    expect(codes(d)).toContain("NO_FIGURES");
  });
});
