import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { renderReview } from "@solvex/core";

const expected = JSON.parse(readFileSync("docs/legacy-prompts/expected-r2.json", "utf-8"));
const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.2 modeling 提示词", () => {
  it("逐字一致（仅 R-2 白名单替换）", () => {
    expect(md("modeling.system.md")).toBe(expected["modeling.SYSTEM_PROMPT"]);
    expect(md("review.md")).toBe(expected["modeling.REVIEW_PROMPT"]);
  });
  it("含编排解析依赖的 '## Model N:' 强制分节", () => {
    expect(md("modeling.system.md")).toContain("## Model N:");
    expect(md("modeling.system.md")).toContain("Each model section MUST start with '## Model N:'");
  });
  it("review.md 保留 5 个占位符且能正确渲染", () => {
    const t = md("review.md");
    for (const p of ["{model_name}", "{problem}", "{model_plan}", "{results}", "{review_path}"])
      expect(t).toContain(p);
    const out = renderReview({ model_name: "Model 1", problem: "P", model_plan: "MP",
      results: "R", review_path: "/tmp/r.md" });
    expect(out).toContain("reviewing the implementation results for Model 1");
    expect(out).toContain("/tmp/r.md");
    expect(out).not.toContain("{model_name}");
  });
  it("以 VERIFICATION_RESULT 双标记结尾（双轨兼容旧版）", () => {
    expect(md("review.md")).toContain("VERIFICATION_RESULT: SATISFIED");
    expect(md("review.md")).toContain("VERIFICATION_RESULT: NEEDS_REVISION");
    expect(md("review.md")).toContain("## Fix Instructions:");
  });
  it("不含 Pi 不存在的 terminate / 旧工具名", () => {
    for (const f of ["modeling.system.md", "modeling.next.md", "review.md"]) {
      expect(md(f)).not.toContain("terminate");
      expect(md(f)).not.toContain("str_replace_editor");
      expect(md(f)).not.toContain("webSearchPrime");
    }
  });
});
