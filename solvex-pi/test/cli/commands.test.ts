import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, existsSync, writeFileSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CLI = "apps/cli/src/index.ts";
const run = (args: string[]) => execFileSync("npx", ["tsx", CLI, ...args], {
  cwd: "/workspace", encoding: "utf-8", env: { ...process.env, SOLVEX_FAKE: "1" }, timeout: 60_000 });

describe("T4.3/T4.4/T4.5 CLI 端到端（FakeRunner）", () => {
  it("solvex run --fake 跑通四阶段，退出码 0、产物兼容、输出 session id", () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-cli-"));
    const problem = join(root, "problem.md");
    writeFileSync(problem, "A simple linear programming problem");
    const out = run(["run", "--fake", "-p", problem, "--session-dir", root, "--concurrency", "3"]);
    expect(out).toContain("session:");
    expect(out).toContain("完成");
    const id = out.match(/session:\s*(\S+)/)?.[1]!;
    const ws = join(root, id);
    expect(existsSync(join(ws, "01_modeling/master_plan.md"))).toBe(true);
    expect(existsSync(join(ws, "02_programming/all_results_summary.md"))).toBe(true);
    expect(existsSync(join(ws, "04_paper/main.tex"))).toBe(true);

    // T4.5 inspect
    const inspect = run(["inspect", id, "--session-dir", root]);
    expect(inspect).toContain("04_paper/main.tex");
    // T4.4 validate（只读，不改产物）
    const before = readFileSync(join(ws, "01_modeling/master_plan.md"));
    const validate = run(["validate", id, "--session-dir", root]);
    expect(validate).toContain("只读检查");
    expect(readFileSync(join(ws, "01_modeling/master_plan.md"))).toEqual(before);
  }, 90_000);

  it("solvex --help 完整列出参数", () => {
    expect(run(["--help"])).toContain("--skip-to-writing");
  }, 30_000);
});
