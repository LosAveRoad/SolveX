import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, readFileSync, statSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { findSolvexEnv, loadSolvexEnv, envFileTarget, persistEnvVar,
         ENV_FILE_OVERRIDE } from "@solvex/pi-runtime";

const KEYS = ["SOLVEX_ENV_A", "SOLVEX_ENV_B", "SOLVEX_ENV_C", "DEEPSEEK_API_KEY"];

describe("项目根 .env 持久化凭据", () => {
  let dir: string;
  let original: Record<string, string | undefined>;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "solvex-env-"));
    original = {};
    for (const k of [...KEYS, ENV_FILE_OVERRIDE]) original[k] = process.env[k];
    for (const k of [...KEYS, ENV_FILE_OVERRIDE]) delete process.env[k];
  });

  afterEach(() => {
    for (const [k, v] of Object.entries(original)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it("加载 .env：注释与引号可解析，shell 已有的同名变量不被覆盖", () => {
    const p = join(dir, ".env");
    writeFileSync(p, "# 注释\n\nSOLVEX_ENV_A=from_file\nSOLVEX_ENV_B=\"quoted value\"\nexport SOLVEX_ENV_C=third\n");
    process.env[ENV_FILE_OVERRIDE] = p;
    process.env.SOLVEX_ENV_A = "from_shell";
    expect(findSolvexEnv()).toBe(p);
    expect(loadSolvexEnv()).toBe(p);
    expect(process.env.SOLVEX_ENV_A).toBe("from_shell");
    expect(process.env.SOLVEX_ENV_B).toBe("quoted value");
    expect(process.env.SOLVEX_ENV_C).toBe("third");
  });

  it("当前工作目录下的 .env 可被定位并加载", () => {
    const p = join(dir, ".env");
    writeFileSync(p, "SOLVEX_ENV_B=cwd_file\n");
    expect(findSolvexEnv({ cwd: dir })).toBe(p);
    expect(loadSolvexEnv({ cwd: dir })).toBe(p);
    expect(process.env.SOLVEX_ENV_B).toBe("cwd_file");
  });

  it("文件缺失或显式路径不存在时静默跳过，不阻断启动", () => {
    process.env[ENV_FILE_OVERRIDE] = join(dir, "missing.env");
    expect(findSolvexEnv()).toBeUndefined();
    expect(loadSolvexEnv()).toBeUndefined();
    expect(process.env.SOLVEX_ENV_A).toBeUndefined();
  });

  it("重复加载幂等", () => {
    const p = join(dir, ".env");
    writeFileSync(p, "SOLVEX_ENV_B=once\n");
    process.env[ENV_FILE_OVERRIDE] = p;
    expect(loadSolvexEnv()).toBe(p);
    expect(loadSolvexEnv()).toBe(p);
    expect(process.env.SOLVEX_ENV_B).toBe("once");
  });

  it("persistEnvVar 替换占位行、保留注释与其它变量、权限 600", () => {
    const p = join(dir, ".env");
    writeFileSync(p, "# 本地凭据\nDEEPSEEK_API_KEY=\nOTHER=keep\n");
    process.env[ENV_FILE_OVERRIDE] = p;
    expect(envFileTarget()).toBe(p);
    const r = persistEnvVar("DEEPSEEK_API_KEY", "sk-probe-123");
    expect(r).toMatchObject({ path: p, envVar: "DEEPSEEK_API_KEY" });
    const raw = readFileSync(p, "utf-8");
    expect(raw).toContain("DEEPSEEK_API_KEY=sk-probe-123");
    expect(raw).toContain("# 本地凭据");
    expect(raw).toContain("OTHER=keep");
    expect((raw.match(/DEEPSEEK_API_KEY=/g) ?? []).length).toBe(1);
    expect(process.env.DEEPSEEK_API_KEY).toBe("sk-probe-123");
    expect(statSync(p).mode & 0o777).toBe(0o600);
  });

  it("注释形式占位与含等号的值也能正确写入", () => {
    const p = join(dir, ".env");
    writeFileSync(p, "# DEEPSEEK_API_KEY=\n");
    process.env[ENV_FILE_OVERRIDE] = p;
    persistEnvVar("DEEPSEEK_API_KEY", "sk-with=equals");
    expect(readFileSync(p, "utf-8")).toContain('DEEPSEEK_API_KEY="sk-with=equals"');
  });

  it("拒绝非法变量名 / 空值 / 换行", () => {
    process.env[ENV_FILE_OVERRIDE] = join(dir, ".env");
    expect(() => persistEnvVar("BAD-NAME", "x")).toThrow();
    expect(() => persistEnvVar("GOOD_NAME", "")).toThrow();
    expect(() => persistEnvVar("GOOD_NAME", "a\nb")).toThrow();
  });
});
