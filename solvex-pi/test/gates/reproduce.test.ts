import { describe, it, expect } from "vitest";
import { mkdtempSync, writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { reproduce, diffResults, captureFiles, restoreFiles } from "@solvex/core";

const dir = () => mkdtempSync(join(tmpdir(), "solvex-repro-"));
const runPy = (body: string) => `import json\n${body}\n`;

describe("ADR-0014 复现门禁：重跑 run.py 并比对 results.json", () => {
  it("缺 run.py / 缺 results.json / results.json 不是合法 JSON", async () => {
    const d = dir();
    expect((await reproduce(d)).reason).toMatch(/run\.py is missing/);
    writeFileSync(join(d, "run.py"), "print(1)\n");
    expect((await reproduce(d)).reason).toMatch(/results\.json is missing/);
    writeFileSync(join(d, "results.json"), "{oops");
    expect((await reproduce(d)).reason).toMatch(/not valid JSON/);
  });
  it("能重新生成一致的结果 → 通过", async () => {
    const d = dir();
    writeFileSync(join(d, "run.py"), runPy(`json.dump({"a": 1.0, "nested": {"b": [1, 2]}}, open("results.json", "w"))`));
    writeFileSync(join(d, "results.json"), JSON.stringify({ a: 1.0, nested: { b: [1, 2] } }));
    expect((await reproduce(d)).ok).toBe(true);
  });
  it("交付的数字与代码重跑结果不一致（过期产物）→ 列出差异", async () => {
    const d = dir();
    writeFileSync(join(d, "run.py"), runPy(`json.dump({"agreement": 0.2956}, open("results.json", "w"))`));
    writeFileSync(join(d, "results.json"), JSON.stringify({ agreement: 0.8681, loo: 0.9 }));
    const r = await reproduce(d);
    expect(r.ok).toBe(false);
    expect(r.mismatches).toEqual(expect.arrayContaining([
      "agreement: delivered 0.8681, re-run produced 0.2956", "loo: delivered 0.9, missing after re-run"]));
  });
  it("脚本崩溃 → 带回 stderr；超时 → 杀掉", async () => {
    const d = dir();
    writeFileSync(join(d, "results.json"), "{}");
    writeFileSync(join(d, "run.py"), "raise NameError('C is not defined')\n");
    const r = await reproduce(d);
    expect(r.ok).toBe(false);
    expect(r.reason).toMatch(/exited with code 1[\s\S]*NameError: C is not defined/);
    writeFileSync(join(d, "run.py"), "import time\ntime.sleep(5)\n");
    expect((await reproduce(d, { timeoutMs: 300 })).reason).toMatch(/did not finish/);
  });
  it("diffResults：数值按相对误差 1e-6 比较，NaN 视为相等", () => {
    expect(diffResults({ x: 1.0000000001, y: NaN }, { x: 1, y: NaN })).toEqual([]);
    expect(diffResults({ x: 1.01 }, { x: 1 })).toHaveLength(1);
  });
});

describe("ADR-0014 文件快照还原（代码执行绕过写拦截，只读靠事后还原）", () => {
  it("改过的恢复、删掉的补回、新建的删除", () => {
    const d = dir();
    mkdirSync(join(d, "m"), { recursive: true });
    writeFileSync(join(d, "m/a.py"), "A"); writeFileSync(join(d, "m/b.csv"), "B");
    const snap = captureFiles([join(d, "m")]);
    writeFileSync(join(d, "m/a.py"), "HACKED");
    writeFileSync(join(d, "m/new.txt"), "N");
    const { restored, removed } = restoreFiles(snap, d);
    expect(readFileSync(join(d, "m/a.py"), "utf-8")).toBe("A");
    expect(existsSync(join(d, "m/new.txt"))).toBe(false);
    expect(restored).toEqual(["m/a.py"]); expect(removed).toEqual(["m/new.txt"]);
  });
});
