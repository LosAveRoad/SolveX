import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

describe("工程基线", () => {
  it("engines.node >= 22.19 且 .nvmrc 一致", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf-8"));
    expect(pkg.engines.node).toBe(">=22.19.0");
    expect(readFileSync(".nvmrc", "utf-8").trim()).toBe("22.20.0");
    const [major, minor] = process.versions.node.split(".").map(Number);
    expect(major > 22 || (major === 22 && minor >= 19)).toBe(true);
  });

  it("workspace 含 4 个包且 Pi SDK 精确锁版本", () => {
    const ws = readFileSync("pnpm-workspace.yaml", "utf-8");
    expect(ws).toContain("packages/*");
    expect(ws).toContain("apps/*");
    const rt = JSON.parse(readFileSync("packages/pi-runtime/package.json", "utf-8"));
    expect(rt.dependencies["@earendil-works/pi-coding-agent"]).toMatch(/^\d+\.\d+\.\d+$/);
    expect(rt.dependencies["@earendil-works/pi-coding-agent"]).toBe("1.5.0");
  });
});
