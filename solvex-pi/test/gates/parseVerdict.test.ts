import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseVerdict } from "@solvex/core";

const dir = () => mkdtempSync(join(tmpdir(), "solvex-verdict-"));
describe("T2.4 双轨 verdict 解析（ADR-03）", () => {
  it("旧文本 SATISFIED -> legacy", () => {
    expect(parseVerdict({ text: "done\nVERIFICATION_RESULT: SATISFIED" }))
      .toMatchObject({ status: "satisfied", source: "legacy" });
  });
  it("NEEDS_REVISION 抽出 fixInstructions", () => {
    const v = parseVerdict({ text: "VERIFICATION_RESULT: NEEDS_REVISION\n## Issues Found:\n1. wrong sum\n## Fix Instructions:\nedit model.py line 3" });
    expect(v.status).toBe("needs_revision");
    expect(v.issuesFound).toContain("wrong sum");
    expect(v.fixInstructions).toContain("edit model.py line 3");
  });
  it("handoff.json 优先 -> structured", () => {
    const d = dir();
    writeFileSync(join(d, "handoff.json"), JSON.stringify({ status: "satisfied", summaryPath: "s.md" }));
    expect(parseVerdict({ dir: d, text: "VERIFICATION_RESULT: NEEDS_REVISION" }))
      .toMatchObject({ status: "satisfied", source: "structured", summaryPath: "s.md" });
  });
  it("两者冲突时以 handoff 为准并记 warn", () => {
    const d = dir();
    writeFileSync(join(d, "handoff.json"), JSON.stringify({ status: "needs_revision" }));
    const v = parseVerdict({ dir: d, text: "VERIFICATION_RESULT: SATISFIED" });
    expect(v.status).toBe("needs_revision");
    expect(v.warn).toContain("冲突");
  });
  it("都缺失 -> unknown（不静默通过）", () => {
    expect(parseVerdict({ text: "no marker" })).toMatchObject({ status: "unknown", source: "none" });
  });
});
