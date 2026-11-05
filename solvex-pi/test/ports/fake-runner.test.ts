import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FakeAgentRunner } from "@solvex/core";

describe("T2.1 AgentRunner 端口 / FakeAgentRunner", () => {
  it("按 role 落盘兼容产物并记录每次 RunRequest", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "solvex-fake-"));
    const runner = new FakeAgentRunner();
    const r = await runner.run({ role: "programming", systemPrompt: "S", task: "T",
      cwd, taskId: "P2-IMPL:model_1" });
    expect(r.settled).toBe(true);
    expect(r.artifacts.length).toBeGreaterThan(0);
    expect(existsSync(join(cwd, "02_programming/model_1/results_summary.md"))).toBe(true);
    expect(existsSync(join(cwd, "02_programming/model_1/figures/fig1.png"))).toBe(true);
    expect(runner.calls).toHaveLength(1);
    expect(runner.calls[0].taskId).toBe("P2-IMPL:model_1");
  });
  it("支持 AbortSignal 与注入失败", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "solvex-fake-"));
    const ac = new AbortController(); ac.abort();
    await expect(new FakeAgentRunner().run({ role: "modeling", systemPrompt: "S", task: "T",
      cwd, taskId: "P1" }, ac.signal)).rejects.toThrow("aborted");
    const r = new FakeAgentRunner({ failTaskIds: ["P1"] });
    await expect(r.run({ role: "modeling", systemPrompt: "S", task: "T", cwd, taskId: "P1" }))
      .rejects.toThrow("fake failure: P1");
  });
});
