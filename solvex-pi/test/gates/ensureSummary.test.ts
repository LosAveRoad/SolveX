import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ensureSummary } from "@solvex/core";

describe("T2.6 ensureSummary（B2/E4）", () => {
  it("结构化占位，不污染产物", () => {
    const d = mkdtempSync(join(tmpdir(), "solvex-sum-"));
    const body = ensureSummary(d, "Model 1");
    expect(readFileSync(join(d, "results_summary.md"), "utf-8")).toBe(body);
    expect(body).not.toContain("<think/>");
    expect(body).not.toContain("'observation':");
    for (const h of ["## Status", "⚠", "## Sanity Checks", "## Figures"]) expect(body).toContain(h);
    expect(Buffer.byteLength(body)).toBeLessThan(2048);
  });
});
