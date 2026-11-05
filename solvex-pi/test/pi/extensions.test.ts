import { describe, it, expect } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runPython, hasPathEscape, safetyExtension, buildCustomTools } from "@solvex/pi-runtime";

const cwd = () => mkdtempSync(join(tmpdir(), "solvex-tool-"));

describe("T3.3 自定义工具扩展", () => {
  it("python_execute 执行 print(1+1) 返回 2", async () => {
    expect((await runPython("print(1+1)", { cwd: cwd() })).trim()).toBe("2");
  });
  it("变量不跨调用持久（第二次 print(x) 报 NameError）", async () => {
    const d = cwd();
    await runPython("x = 42\nprint(x)", { cwd: d });
    await expect(runPython("print(x)", { cwd: d })).rejects.toThrow(/NameError/);
  });
  it("非零退出返回错误", async () => {
    await expect(runPython("import sys; sys.exit(3)", { cwd: cwd() })).rejects.toThrow(/exited 3/);
  });
  it("buildCustomTools 参数 schema 必填校验生效", () => {
    const tools = buildCustomTools();
    expect(tools.map((t: any) => t.name)).toEqual(
      expect.arrayContaining(["python_execute", "arxiv_search", "web_search", "webReader"]));
    const py: any = tools.find((t: any) => t.name === "python_execute");
    expect(py.parameters.required).toContain("code");
  });
  it("hasPathEscape 拦截 .. 与绝对路径", () => {
    expect(hasPathEscape({ path: "../../etc/passwd" })).toBe(true);
    expect(hasPathEscape({ file_path: "C:/Windows/system32" })).toBe(true);
    expect(hasPathEscape({ path: "02_programming/model_1/a.py" })).toBe(false);
  });
  it("safetyExtension 的 tool_call 拦截越界写入（R5/R11）", async () => {
    let handler: any;
    safetyExtension({ on: (_e: string, h: any) => { handler = h; } }, ["02_programming/model_1/"]);
    expect((await handler({ toolName: "write", input: { path: "../../etc/passwd" } })).block).toBe(true);
    expect((await handler({ toolName: "write", input: { path: "02_programming/model_2/a.py" } })).block).toBe(true);
    expect(await handler({ toolName: "write", input: { path: "02_programming/model_1/a.py" } })).toBeUndefined();
    expect(await handler({ toolName: "read", input: { path: "../outside" } })).toBeDefined();
  });
});
