import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
const expected = JSON.parse(readFileSync("docs/legacy-prompts/expected-r2.json", "utf-8"));
const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.3 programming 提示词", () => {
  it("逐字一致", () => {
    expect(md("programming.system.md")).toBe(expected["programming.SYSTEM_PROMPT"]);
    expect(md("programming.next.md")).toBe(expected["programming.NEXT_STEP_PROMPT"]);
  });
  it("results_summary 的 6 个固定小节", () => {
    const t = md("programming.system.md");
    for (const h of ["## Key Numerical Results", "## Sanity Checks", "## Model Parameters",
                     "## Data Files Generated", "## Figures", "## Issues or Limitations"])
      expect(t).toContain(h);
  });
  it("VERIFICATION_RESULT 双标记", () => {
    const t = md("programming.system.md");
    expect(t).toContain("VERIFICATION_RESULT: SATISFIED");
    expect(t).toContain("VERIFICATION_RESULT: NEEDS_REVISION");
  });
  it("图片规范 Agg/dpi=300 与 {output_dir}", () => {
    expect(md("programming.system.md")).toContain("matplotlib.use('Agg')");
    expect(md("programming.system.md")).toContain("dpi=300");
    expect(md("programming.next.md")).toContain("{output_dir}");
  });
  it("python_execute 变量不持久语义保留", () => {
    expect(md("programming.system.md")).toContain("Variables do NOT persist between calls");
  });
});
