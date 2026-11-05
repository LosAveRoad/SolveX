import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { parseModels, sectionFor } from "@solvex/core";

const plan = readFileSync("fixtures/legacy-session/01_modeling/master_plan.md", "utf-8");
describe("T2.3 Master Plan 解析契约", () => {
  it("解析出 N 个 Model N", () => expect(parseModels(plan)).toEqual(["Model 1", "Model 2"]));
  it("无分节时降级 ['Model 1']（旧行为）", () => expect(parseModels("no sections")).toEqual(["Model 1"]));
  it("sectionFor 截到下一个 ## Model / ## Integration 之前", () => {
    const s = sectionFor(plan, "Model 1");
    expect(s).toContain("Baseline Linear Program");
    expect(s).not.toContain("Bayesian Sensitivity");
    expect(sectionFor(plan, "Model 2")).toContain("Posterior");
  });
  it("特殊字符标题不炸正则", () => {
    expect(parseModels("## Model 1: A (B) [C]\n## Model 2: X+Y")).toEqual(["Model 1", "Model 2"]);
    expect(() => sectionFor(plan, "Model 1: (a+b)")).not.toThrow();
  });
});
