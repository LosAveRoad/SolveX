import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  modelingSystem, injectToolList, toolDescriptorsFor, renderToolList,
  fallbackToolCatalog, TOOL_LIST_PLACEHOLDER, ROLE_TOOLS, SDK_BUILTIN_TOOLS,
  AVAILABLE_TOOLS, validateRoleTools, EventBus,
} from "@solvex/core";
import {
  discoverToolCatalog, discoveredToolNames, resetToolCatalogForTest,
  SDK_TOOLS_MODULE_PATH, PiAgentRunner,
} from "@solvex/pi-runtime";
import { makeFakeSdk } from "../pi/fakeSdk.js";

const cwd = () => mkdtempSync(join(tmpdir(), "solvex-tools-"));

describe("ADR-0011 工具清单由代码发现，提示词不再自带版本", () => {
  it("从已安装的 SDK 注册表 + 自定义工具发现，含描述且不含幽灵工具", async () => {
    resetToolCatalogForTest();
    expect(existsSync(SDK_TOOLS_MODULE_PATH)).toBe(true);
    const catalog = await discoverToolCatalog();
    const names = await discoveredToolNames();
    for (const t of SDK_BUILTIN_TOOLS) expect(names).toContain(t);
    expect(names).toContain("python_execute");
    // SDK 1.5.0 注册表里还有 powershell；说明清单确实读自 SDK，而非抄来的常量
    expect(names).toContain("powershell");
    for (const ghost of ["arxiv_search", "web_search", "webReader", "terminate"])
      expect(names).not.toContain(ghost);
    for (const t of catalog) expect(t.description.length).toBeGreaterThan(0);
    expect(catalog.find((t) => t.name === "read")?.description).toContain("Read file");
    expect(catalog.find((t) => t.name === "python_execute")?.description).toContain("fresh process");
  });

  it("发现结果覆盖所有角色白名单（validateRoleTools 仍然成立）", async () => {
    const names = new Set(await discoveredToolNames());
    expect(validateRoleTools()).toEqual([]);
    for (const [role, tools] of Object.entries(ROLE_TOOLS)) {
      for (const t of tools) expect(names.has(t), `${role}: ${t}`).toBe(true);
    }
    for (const t of AVAILABLE_TOOLS) expect(names.has(t)).toBe(true);
  });

  it("renderToolList / injectToolList 生成权威清单并替换占位符", async () => {
    const catalog = await discoverToolCatalog();
    const descriptors = toolDescriptorsFor(ROLE_TOOLS.modeling, catalog);
    const list = renderToolList(descriptors);
    expect(list).toContain("AVAILABLE TOOLS (discovered");
    expect(list).toContain("- python_execute:");
    expect(list).toContain("Only these tools are registered.");
    const prompt = injectToolList(modelingSystem(), descriptors);
    expect(prompt).not.toContain(TOOL_LIST_PLACEHOLDER);
    expect(prompt).toContain("AVAILABLE TOOLS (discovered");
    expect(prompt).not.toContain("arxiv_search");
    // 未被该角色白名单选中的工具不能出现在它的提示词里
    expect(prompt).not.toContain("- powershell:");
  });

  it("没有占位符的提示词原样返回；空清单与兜底清单也不抛错", () => {
    expect(injectToolList("plain prompt", [])).toBe("plain prompt");
    expect(injectToolList(`a ${TOOL_LIST_PLACEHOLDER} b`, [])).toContain("no tools are registered");
    expect(fallbackToolCatalog("review").map((t) => t.name)).toEqual(ROLE_TOOLS.review);
  });

  it("PiAgentRunner 注入的清单与本次 session 的 tools 完全一致", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run({
      role: "modeling", systemPrompt: modelingSystem(), task: "TASK", cwd: cwd(),
      taskId: "P1", phase: 1, tools: ROLE_TOOLS.modeling,
    });
    const systemPrompt: string = f.loaderOptions[0].systemPromptOverride();
    expect(systemPrompt).not.toContain(TOOL_LIST_PLACEHOLDER);
    const listed = [...systemPrompt.matchAll(/^- ([a-z_]+):/gm)].map((m) => m[1]);
    expect(listed).toEqual(ROLE_TOOLS.modeling);
    expect(f.createOptions[0].tools).toEqual(listed);
  });

  it("混入幽灵工具时，session 与提示词同时过滤掉它们", async () => {
    const f = makeFakeSdk();
    await new PiAgentRunner({ bus: new EventBus(), sdk: f.sdk }).run({
      role: "modeling", systemPrompt: modelingSystem(), task: "TASK", cwd: cwd(),
      taskId: "P1", phase: 1,
      tools: [...ROLE_TOOLS.modeling, "arxiv_search", "web_search", "webReader"],
    });
    const systemPrompt: string = f.loaderOptions[0].systemPromptOverride();
    expect(f.createOptions[0].tools).toEqual(ROLE_TOOLS.modeling);
    expect(systemPrompt).not.toContain("arxiv_search");
    expect(systemPrompt).not.toContain("webReader");
  });
});
