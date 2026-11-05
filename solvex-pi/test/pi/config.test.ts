import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ConfigStore, thinkingLevelsForModel, phaseOverrides } from "@solvex/pi-runtime";
import { DEFAULT_CONFIG, THINKING_LEVELS } from "@solvex/core";

describe("T3.1 配置骨架", () => {
  it("默认 concurrency=3 / strict=false / byPhase 五档 / 7 档 thinking / 无明文密钥", () => {
    const c = new ConfigStore(join(mkdtempSync(join(tmpdir(), "solvex-cfg-")), "cfg.json")).load();
    expect(c.concurrency).toBe(3);
    expect(c.strict).toBe(false);
    expect(Object.keys(c.byPhase)).toHaveLength(5);
    expect(c.thinkingLevels).toEqual([...THINKING_LEVELS]);
    expect(JSON.stringify(c)).not.toMatch(/sk-[A-Za-z0-9]{12,}/);
  });
  it("save 后 load 回读一致", () => {
    const p = join(mkdtempSync(join(tmpdir(), "solvex-cfg-")), "cfg.json");
    const s = new ConfigStore(p);
    s.save({ concurrency: 5, strict: true, defaults: { provider: "anthropic", model: "claude-x", thinkingLevel: "high" } });
    const c = s.load();
    expect(c.concurrency).toBe(5);
    expect(c.strict).toBe(true);
    expect(c.defaults.model).toBe("claude-x");
    expect(JSON.parse(readFileSync(p, "utf-8")).byPhase.P1.thinkingLevel).toBe("high");
  });
  it("phaseOverrides 未配置时回落 defaults", () => {
    const o = phaseOverrides(DEFAULT_CONFIG, "P1");
    expect(o.thinkingLevel).toBe("high");
    expect(o.model).toBeUndefined();
  });
  it("thinkingLevelsForModel 按 reasoning 能力裁剪", () => {
    expect(thinkingLevelsForModel({ reasoning: true } as any)).toHaveLength(7);
    expect(thinkingLevelsForModel({ reasoning: false } as any)).toEqual(["off"]);
    expect(thinkingLevelsForModel(undefined)).toEqual(["off"]);
  });
});
