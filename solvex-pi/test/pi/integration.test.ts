import { describe, it, expect } from "vitest";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EventBus, prepareWorkspace, modelingSystem, renderPlan } from "@solvex/core";
import { PiAgentRunner } from "@solvex/pi-runtime";

const MODEL = process.env.PI_TEST_MODEL;

describe.skipIf(!MODEL)("T3.5 真实模型单阶段集成（需 PI_TEST_MODEL）", () => {
  it("P1 生成含 '## Model 1:' 的 master_plan.md", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-real-"));
    const ws = prepareWorkspace({ root, sessionId: "real", problem: "A simple linear programming problem" });
    const runner = new PiAgentRunner({ bus: new EventBus() });
    await runner.run({ role: "modeling", systemPrompt: modelingSystem(),
      task: renderPlan({ input_text: "A simple linear programming problem", data_info: "",
        master_plan_path: join(ws.paths.modeling, "master_plan.md") }),
      cwd: ws.dir, taskId: "P1", phase: 1, maxTurns: 25 });
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
  }, 600_000);
});
