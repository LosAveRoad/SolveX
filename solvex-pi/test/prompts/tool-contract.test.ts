import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  EventBus, ROLE_TOOLS, SDK_BUILTIN_TOOLS, CUSTOM_TOOL_NAMES,
  AVAILABLE_TOOLS, validateRoleTools,
} from "@solvex/core";
import { PiAgentRunner, buildCustomTools } from "@solvex/pi-runtime";
import { makeFakeSdk } from "../pi/fakeSdk.js";

const cwd = () => mkdtempSync(join(tmpdir(), "solvex-contract-"));

/**
 * ADR-0008 回归：真实 DeepSeek 端到端跑 2026 MCM Problem C 时发现
 *  (1) 模型从不调用 write，P1 不产出 master_plan.md；
 *  (2) 模型反复用 bash+curl 请求 arxiv，超时后无限重试。
 * 两者同源于「白名单/提示词里声明了运行时并不存在的工具」。
 */
describe("ADR-0008 工具契约回归", () => {
  it("SDK 内置工具 + 自定义工具 = 运行时真实可用集合", () => {
    expect([...SDK_BUILTIN_TOOLS].sort()).toEqual(
      ["bash", "edit", "find", "grep", "ls", "read", "write"]);
    expect(CUSTOM_TOOL_NAMES).toEqual(["python_execute"]);
    expect(AVAILABLE_TOOLS.size).toBe(8);
    expect(validateRoleTools()).toEqual([]);
  });

  it("buildCustomTools 注册的名字与 CUSTOM_TOOL_NAMES 完全一致", () => {
    expect(buildCustomTools().map((t: any) => t.name)).toEqual([...CUSTOM_TOOL_NAMES]);
  });

  it("modeling 白名单含 write、不含任何联网检索工具", () => {
    expect(ROLE_TOOLS.modeling).toContain("write");
    for (const ghost of ["arxiv_search", "web_search", "webReader"])
      expect(ROLE_TOOLS.modeling).not.toContain(ghost);
  });

  it("ADR-0009：writing 放宽后仍全部是真实可注册的工具", () => {
    expect(validateRoleTools()).toEqual([]);
    for (const t of ROLE_TOOLS.writing) expect(AVAILABLE_TOOLS.has(t)).toBe(true);
  });

  it("runner 注入 customTools，并把未知工具从白名单里过滤掉", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run({
      role: "modeling", systemPrompt: "SYS", task: "TASK", cwd: cwd(),
      taskId: "P1", phase: 1,
      tools: [...ROLE_TOOLS.modeling, "arxiv_search", "web_search"],
    });
    expect(f.createOptions[0].tools).toEqual(ROLE_TOOLS.modeling);
    expect(f.createOptions[0].tools).not.toContain("arxiv_search");
    expect(f.createOptions[0].customTools.map((t: any) => t.name))
      .toEqual([...CUSTOM_TOOL_NAMES]);
  });
});
