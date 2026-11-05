import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { ROLE_TOOLS } from "@solvex/core";

const md = (f: string) => readFileSync(`packages/core/src/prompts/${f}`, "utf-8");

describe("T1.6 提示词 ↔ 工具白名单一致性（R4）", () => {
  it("review 为只读白名单（A2/F3 根因）", () => {
    expect(ROLE_TOOLS.review).toEqual(["read", "grep", "find", "ls"]);
    expect(ROLE_TOOLS.review).not.toContain("write");
    expect(ROLE_TOOLS.review).not.toContain("edit");
  });
  it("提示词列举的工具全部在对应角色白名单中", () => {
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
});
