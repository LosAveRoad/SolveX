import { describe, it, expect } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  prepareWorkspace, writeRuntime, readRuntime, buildRuntimeConfig, sanitizeOverrides,
  runtimeSummary, listAllRuns, findRun, runsRoot, runDir, scanArtifacts,
  DEFAULT_CONFIG, type RuntimeSnapshot,
} from "@solvex/core";

const root = () => mkdtempSync(join(tmpdir(), "solvex-runs-"));
const snapshot = (id: string, workspaceId?: string): RuntimeSnapshot => ({
  id, ...(workspaceId ? { workspaceId } : {}), createdAt: new Date().toISOString(),
  config: buildRuntimeConfig(DEFAULT_CONFIG, { concurrency: 2 }),
  overrides: { concurrency: 2 }, inputs: { files: ["p.md"] },
});

describe("一道题一个工作区 · 多次运行互不覆盖", () => {
  it("helper 生成 workspaces/{id}/runs/{runId} 布局", () => {
    const r = root();
    expect(runsRoot(r, "ws-1")).toBe(join(r, "ws-1", "runs"));
    expect(runDir(r, "ws-1", "run-1")).toBe(join(r, "ws-1", "runs", "run-1"));
  });

  it("sanitizeOverrides 只保留白名单字段，丢弃凭据与非法档位", () => {
    const out = sanitizeOverrides({
      concurrency: 99, strict: true,
      defaults: { provider: "openai", model: "gpt-5", thinkingLevel: "ULTRA" },
      byPhase: { P1: { model: "m", thinkingLevel: "high" }, NOPE: { model: "x" } },
      scopedModels: ["a", 42, "b"],
      apiKey: "sk-plain-secret", credentials: [{ masked: "xx" }],
    });
    expect(out.concurrency).toBe(16);
    expect(out.strict).toBe(true);
    expect(out.defaults).toEqual({ provider: "openai", model: "gpt-5" });
    expect(out.byPhase).toEqual({ P1: { model: "m", thinkingLevel: "high" } });
    expect(out.scopedModels).toEqual(["a", "b"]);
    expect(JSON.stringify(out)).not.toContain("sk-plain-secret");
    expect(JSON.stringify(out)).not.toContain("credentials");
    expect(sanitizeOverrides(null)).toEqual({});
    expect(sanitizeOverrides("nope")).toEqual({});
  });

  it("buildRuntimeConfig 是逐 run 快照：改全局配置不影响已有快照", () => {
    const a = buildRuntimeConfig(DEFAULT_CONFIG, { concurrency: 1, strict: true });
    const changed = { ...DEFAULT_CONFIG, concurrency: 8, defaults: { ...DEFAULT_CONFIG.defaults, model: "later" } };
    const b = buildRuntimeConfig(changed, {});
    expect(a.concurrency).toBe(1); expect(a.strict).toBe(true);
    expect(a.defaults.model).toBeUndefined();
    expect(b.concurrency).toBe(8); expect(b.defaults.model).toBe("later");
    expect(runtimeSummary(snapshot("r"))).toMatchObject({ model: "服务端默认", concurrency: 2, strict: false });
  });

  it("同一工作区多个 run 目录独立落盘；索引按 workspaceId 过滤", () => {
    const r = root();
    const runs = runsRoot(r, "ws-a");
    const one = prepareWorkspace({ root: runs, sessionId: "run-1", problem: "A" });
    const two = prepareWorkspace({ root: runs, sessionId: "run-2", problem: "B" });
    writeRuntime(one, snapshot("run-1", "ws-a"));
    writeRuntime(two, snapshot("run-2", "ws-a"));
    writeFileSync(join(one.paths.paper, "main.tex"), "one");
    writeFileSync(join(two.paths.paper, "main.tex"), "two");
    expect(existsSync(join(one.paths.paper, "main.tex"))).toBe(true);
    expect(readRuntime(two)?.id).toBe("run-2");
    expect(scanArtifacts(one).some((x) => x.path === "runtime.json")).toBe(false);
    expect(scanArtifacts(one).some((x) => x.path === "04_paper/main.tex")).toBe(true);

    const legacy = join(r, "sessions");
    prepareWorkspace({ root: legacy, sessionId: "legacy-run", problem: "C" });

    const all = listAllRuns({ workspaceRoot: r, sessionRoot: legacy });
    expect(all.map((x) => x.id).sort()).toEqual(["legacy-run", "run-1", "run-2"]);
    expect(listAllRuns({ workspaceRoot: r, workspaceId: "ws-a" }).map((x) => x.id)).toHaveLength(2);
    expect(listAllRuns({ workspaceRoot: r, workspaceId: "ws-a" })[0].workspaceId).toBe("ws-a");
    expect(findRun("run-2", { workspaceRoot: r, sessionRoot: legacy })?.dir).toBe(two.dir);
    expect(findRun("legacy-run", { workspaceRoot: r, sessionRoot: legacy })?.dir).toBe(join(legacy, "legacy-run"));
    expect(findRun("../escape", { workspaceRoot: r, sessionRoot: legacy })).toBeUndefined();
  });

  it("工作区之间互不可见：另一个题目的 run 不出现在索引里", () => {
    const r = root();
    mkdirSync(join(r, "ws-b"), { recursive: true });
    prepareWorkspace({ root: runsRoot(r, "ws-a"), sessionId: "a1", problem: "A" });
    prepareWorkspace({ root: runsRoot(r, "ws-b"), sessionId: "b1", problem: "B" });
    expect(listAllRuns({ workspaceRoot: r, workspaceId: "ws-a" }).map((x) => x.id)).toEqual(["a1"]);
    expect(listAllRuns({ workspaceRoot: r, workspaceId: "ws-b" }).map((x) => x.id)).toEqual(["b1"]);
  });
});
