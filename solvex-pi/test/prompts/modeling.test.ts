import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { renderReview, TOOL_LIST_PLACEHOLDER } from "@solvex/core";

const expected = JSON.parse(readFileSync("docs/legacy-prompts/expected-r2.json", "utf-8"));
const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");
const tail = (text: string, heading: string) => text.slice(text.indexOf(heading));
const between = (text: string, start: string, end: string) =>
  text.slice(text.indexOf(start), text.indexOf(end));

describe("T1.2 modeling 提示词", () => {
  it("其余资产仍逐字一致；modeling.system.md 仅清理工具清单（ADR-0011）", () => {
    expect(md("review.md")).toBe(expected["modeling.REVIEW_PROMPT"]);
    const live = md("modeling.system.md");
    const legacy: string = expected["modeling.SYSTEM_PROMPT"];
    expect(live).toContain(TOOL_LIST_PLACEHOLDER);
    // 归档基线本身不动，历史证据链保留
    expect(legacy).toContain("AVAILABLE TOOLS:");
    expect(legacy).toContain("web_search");
    // 除工具段与 WORKFLOW 之外的全部章节逐字保留
    expect(live.slice(0, live.indexOf(TOOL_LIST_PLACEHOLDER)))
      .toBe(legacy.slice(0, legacy.indexOf("AVAILABLE TOOLS:")));
    expect(between(live, "RESPONSE FORMAT:", "PHILOSOPHY"))
      .toBe(between(legacy, "RESPONSE FORMAT:", "PHILOSOPHY"));
    expect(between(live, "PHILOSOPHY", "WORKFLOW:"))
      .toBe(between(legacy, "PHILOSOPHY", "WORKFLOW:"));
    for (const h of ["MASTER PLAN FORMAT — Use EXACTLY this structure:", "IMPORTANT RULES:"])
      expect(tail(live, h)).toBe(tail(legacy, h));
  });
  it("提示词资产里不再声明任何工具（工具清单改由代码发现）", () => {
    const live = md("modeling.system.md");
    for (const t of ["arxiv_search", "web_search", "webReader", "webSearchPrime",
                     "python_execute", "str_replace_editor", "terminate"])
      expect(live).not.toContain(t);
    expect(live).not.toContain("AVAILABLE TOOLS:");
    // 正文里的 write/read 是自然语言动词，不判违规；只禁止「工具清单式」声明
    expect(live).not.toMatch(/^- (read|write|edit|bash|grep|find|ls|python_execute):/m);
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
