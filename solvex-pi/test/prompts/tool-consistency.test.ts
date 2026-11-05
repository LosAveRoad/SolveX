import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { ROLE_TOOLS, AVAILABLE_TOOLS, validateRoleTools } from "@solvex/core";

const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.6 提示词 ↔ 工具白名单一致性（R4）", () => {
  it("review 为只读白名单（A2/F3 根因）", () => {
    expect(ROLE_TOOLS.review).toEqual(["read", "grep", "find", "ls"]);
    expect(ROLE_TOOLS.review).not.toContain("write");
    expect(ROLE_TOOLS.review).not.toContain("edit");
  });
  it("逐字资产保留旧工具名（运行时由 OFFLINE_PLAN_POLICY 覆盖）", () => {
    const modeled = md("modeling.system.md");
    for (const t of ["arxiv_search", "web_search", "webReader", "python_execute", "write", "edit"])
      expect(modeled).toContain(t);
    const prog = md("programming.system.md");
    for (const t of ["python_execute", "write", "edit"]) expect(prog).toContain(t);
  });
  it("所有白名单工具名均为合法标识符且无重复", () => {
    for (const [role, tools] of Object.entries(ROLE_TOOLS)) {
      expect(new Set(tools).size, role).toBe(tools.length);
      for (const t of tools) expect(t).toMatch(/^[a-zA-Z_][a-zA-Z0-9_]*$/);
    }
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
