import { describe, it, expect } from "vitest";
import { parseArgs, HELP } from "../../apps/cli/src/args.js";

describe("T4.1 CLI 参数解析（与旧版 1:1 兼容）", () => {
  it("-p/-d/-r/--from-model/-w/--session-dir/--strict/--concurrency 全覆盖", () => {
    const a = parseArgs(["run", "-p", "p.md", "-d", "d1", "-d", "d2", "-r", "s1",
      "--from-model", "2", "-w", "--session-dir", "/tmp/s", "--strict", "--concurrency", "5"]);
    expect(a.command).toBe("run");
    expect(a.problem).toBe("p.md");
    expect(a.data).toEqual(["d1", "d2"]);
    expect(a.resume).toBe("s1");
    expect(a.fromModel).toBe(2);
    expect(a.skipToWriting).toBe(true);
    expect(a.sessionDir).toBe("/tmp/s");
    expect(a.strict).toBe(true);
    expect(a.concurrency).toBe(5);
  });
  it("默认值：concurrency=3 / strict=false / 无参进入交互", () => {
    const a = parseArgs(["run"]);
    expect(a.concurrency).toBe(3);
    expect(a.strict).toBe(false);
    expect(a.interactive).toBe(true);
  });
  it("serve / inspect / validate 子命令与 --port", () => {
    expect(parseArgs(["serve", "--port", "9000"]).port).toBe(9000);
    expect(parseArgs(["inspect", "abc"]).sessionId).toBe("abc");
    expect(parseArgs(["validate", "abc"]).command).toBe("validate");
  });
  it("帮助文本列出旧参数与新增参数", () => {
    for (const k of ["--problem", "--data", "--resume", "--skip-to-writing",
                     "--concurrency", "--strict"])
      expect(HELP).toContain(k);
  });

  it("演示模式不作为公开选项暴露，未知选项直接报错", () => {
    expect(HELP).not.toContain("--fake");
    expect(HELP).not.toContain("FakeAgentRunner");
    expect(HELP).toContain("模型设置");
    const a = parseArgs(["run", "-p", "p.md"]);
    expect("fake" in a).toBe(false);
    expect(() => parseArgs(["run", "--fake"])).toThrow(/未知选项/);
  });
});
