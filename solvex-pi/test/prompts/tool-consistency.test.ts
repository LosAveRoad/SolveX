import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { ROLE_TOOLS, AVAILABLE_TOOLS, validateRoleTools, TOOL_LIST_PLACEHOLDER } from "@solvex/core";

const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.6 提示词 ↔ 工具白名单一致性（R4）", () => {
  it("review 不给写工具（A2/F3 根因）；ADR-0014 起可以跑代码，改动由编排层快照还原", () => {
    expect(ROLE_TOOLS.review).toEqual(["read", "grep", "find", "ls", "bash", "python_execute"]);
    expect(ROLE_TOOLS.review).not.toContain("write");
    expect(ROLE_TOOLS.review).not.toContain("edit");
  });
  it("ADR-0011：modeling 提示词不含工具名，只保留发现占位符", () => {
    const modeled = md("modeling.system.md");
    expect(modeled).toContain(TOOL_LIST_PLACEHOLDER);
    for (const t of ["arxiv_search", "web_search", "webReader", "python_execute",
                     "str_replace_editor", "terminate"])
      expect(modeled).not.toContain(t);
    expect(modeled).not.toContain("AVAILABLE TOOLS:");
    expect(modeled).not.toMatch(/^- (read|write|edit|bash|grep|find|ls|python_execute):/m);
    // 其余逐字资产尚未清理，仍保留旧工具名；它们以后也可用同一个占位符接入。
    const prog = md("programming.system.md");
    for (const t of ["python_execute", "write", "edit"]) expect(prog).toContain(t);
  });
  it("所有白名单工具名均为合法标识符且无重复", () => {
    for (const [role, tools] of Object.entries(ROLE_TOOLS)) {
      expect(new Set(tools).size, role).toBe(tools.length);
      for (const t of tools) expect(t).toMatch(/^[a-zA-Z_][a-zA-Z0-9_]*$/);
    }
  });
  it("ADR-0009：writing 具备工作区发现能力；review 没有 write/edit 工具", () => {
    for (const t of ["read", "write", "edit", "ls", "find", "grep", "bash"])
      expect(ROLE_TOOLS.writing).toContain(t);
    expect(ROLE_TOOLS.review).not.toContain("write");
    expect(ROLE_TOOLS.review).not.toContain("edit");
  });
  it("R-2：白名单 ⊆ 运行时真实可用工具，且 modeling 不含联网检索工具", () => {
    expect(validateRoleTools()).toEqual([]);
    for (const [role, tools] of Object.entries(ROLE_TOOLS))
      for (const t of tools) expect(AVAILABLE_TOOLS.has(t), `${role}: ${t}`).toBe(true);
    expect(ROLE_TOOLS.modeling).toContain("write");
    for (const ghost of ["arxiv_search", "web_search", "webReader"])
      expect(ROLE_TOOLS.modeling).not.toContain(ghost);
  });
});
