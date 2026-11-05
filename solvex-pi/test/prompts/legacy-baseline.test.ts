import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

const base = JSON.parse(readFileSync("docs/legacy-prompts/baseline.json", "utf-8"));

describe("T1.1 legacy 基准", () => {
  it("18 段原文归档完整", () => {
    expect(Object.keys(base)).toHaveLength(18);
    expect(Object.values(base).every((v) => typeof v === "string" && v.length > 0)).toBe(true);
  });
  it("modeling 三常量原文长度与源文件一致", () => {
    expect(base["modeling.SYSTEM_PROMPT"]).toHaveLength(4963);
    expect(base["modeling.NEXT_STEP_PROMPT"]).toHaveLength(413);
    expect(base["modeling.REVIEW_PROMPT"]).toHaveLength(1453);
  });
  it("内联 5 段 f-string 原文已提取（最易漏资产）", () => {
    for (const k of ["inline.modeling_prompt.0", "inline.programming_prompt.0",
                     "inline.programming_prompt.1", "inline.fix_prompt.0",
                     "inline.write_prompt.0"]) expect(base[k]).toBeTruthy();
  });
});
