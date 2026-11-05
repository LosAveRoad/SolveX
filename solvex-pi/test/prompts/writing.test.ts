import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
const expected = JSON.parse(readFileSync("docs/legacy-prompts/expected-r2.json", "utf-8"));
const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.4 writing 提示词", () => {
  it("逐字一致", () => {
    expect(md("writing.system.md")).toBe(expected["writing.SYSTEM_PROMPT"]);
    expect(md("writing.next.md")).toBe(expected["writing.NEXT_STEP_PROMPT"]);
  });
  it("7 条 CRITICAL RULES 全在", () => {
    const t = md("writing.system.md");
    expect(t).toContain("CRITICAL RULES — DO NOT VIOLATE");
    for (const k of ["USE ONLY the results provided", "INSERT EVERY figure",
                     "CROSS-CHECK numbers", "20-30 pages"]) expect(t).toContain(k);
  });
  it("LaTeX 图片路径模板（以代码为准，非 README 的 03_figures）", () => {
    expect(md("writing.system.md")).toContain("../02_programming/model_N/figures/");
    expect(md("writing.system.md")).toContain("NO single quotes around the path");
  });
  it("不含 terminate / 旧工具名", () => {
    for (const f of ["writing.system.md", "writing.next.md"]) {
      expect(md(f)).not.toContain("terminate");
      expect(md(f)).not.toContain("str_replace_editor");
    }
  });
});
