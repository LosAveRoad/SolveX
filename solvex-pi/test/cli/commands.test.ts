import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const CLI = "apps/cli/src/index.ts";
const cwd = fileURLToPath(new URL("../../", import.meta.url));
const run = (args: string[], env: Record<string, string> = {}) =>
  execFileSync(process.execPath, ["--import", "tsx", CLI, ...args], {
    cwd, encoding: "utf-8", env: { ...process.env, ...env }, timeout: 60_000 });

/** 预置一次「已完成」的产物树，让 inspect / validate 无需模型即可验证。 */
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "solvex-cli-"));
  const id = "fixture-session";
  const ws = join(root, id);
  for (const d of ["00_problem", "01_modeling", "02_programming/model_1", "04_paper"])
    mkdirSync(join(ws, d), { recursive: true });
  writeFileSync(join(ws, ".solvex-meta.json"), JSON.stringify({
    id, status: "completed", created_at: new Date().toISOString(), problem: "A" }));
  writeFileSync(join(ws, "00_problem/problem.md"), "A simple linear programming problem");
  writeFileSync(join(ws, "01_modeling/master_plan.md"), "## Model 1: Linear program\nSolve it.\n");
  writeFileSync(join(ws, "02_programming/model_1/model.py"), "print('ok')\n");
  writeFileSync(join(ws, "02_programming/model_1/results_summary.md"),
    ["## Status", "ok", "## Key Numerical Results", "objective = 1.0",
     "## Sanity Checks", "done", "## Model Parameters", "none",
     "## Data Files Generated", "model.py", "## Figures", "none",
     "## Issues or Limitations", "none", ""].join("\n"));
  writeFileSync(join(ws, "04_paper/main.tex"),
    "\\documentclass{article}\\begin{document}ok\\end{document}\n");
  return { root, id, ws };
}

describe("CLI 命令（正常模式；演示 runner 仅由内部测试注入）", () => {
  it("--help 完整列出参数，且不含演示模式选项", () => {
    const help = run(["--help"]);
    expect(help).toContain("--skip-to-writing");
    expect(help).not.toContain("--fake");
    expect(help).not.toContain("FakeAgentRunner");
    expect(help).toContain("模型设置");
  }, 30_000);

  it("演示开关与旧环境变量都不再被接受", () => {
    expect(() => run(["run", "--fake"])).toThrow();
    let threw = false;
    try { run(["run", "--fake"], { SOLVEX_FAKE: "1" }); } catch { threw = true; }
    expect(threw).toBe(true);
  }, 60_000);

  it("inspect / validate 对已有产物工作，且 validate 为只读", () => {
    const { root, id, ws } = fixture();
    const inspect = run(["inspect", id, "--session-dir", root]);
    expect(inspect).toContain("04_paper/main.tex");
    const before = readFileSync(join(ws, "01_modeling/master_plan.md"));
    const validate = run(["validate", id, "--session-dir", root]);
    expect(validate).toContain("只读检查");
    expect(readFileSync(join(ws, "01_modeling/master_plan.md"))).toEqual(before);
  }, 60_000);
});
