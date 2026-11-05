import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";

describe("T1.7 非主链路提示词归档", () => {
  it("7 个 legacy .py 存在", () => {
    for (const f of ["manus", "mcp", "planning", "swe", "toolcall", "browser", "visualization"])
      expect(existsSync(`docs/legacy-prompts/${f}.py`)).toBe(true);
  });
  it("prompts/index.ts 不导出它们（防止误加载）", () => {
    const idx = readFileSync("packages/core/src/prompts/index.ts", "utf-8");
    for (const f of ["manus", "mcp", "planning", "swe", "toolcall", "browser"])
      expect(idx).not.toContain(f);
  });
  it("visualization 单独保留为可选 stage", () => {
    expect(existsSync("packages/core/src/prompts/visualization.system.md")).toBe(true);
    expect(readFileSync("packages/core/src/prompts/visualization.system.md", "utf-8").length).toBeGreaterThan(1000);
  });
});
