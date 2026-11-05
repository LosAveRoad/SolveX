import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync, writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { prepareWorkspace, ingestData, zipWorkspace, unzipWorkspace, listSessions,
  modelDirName, writeSessionMeta, scanArtifacts } from "@solvex/core";

const root = () => mkdtempSync(join(tmpdir(), "solvex-ws-"));

describe("T2.2 workspace 契约", () => {
  it("create 生成 §2.5 全部目录与 problem.md", () => {
    const ws = prepareWorkspace({ root: root(), sessionId: "s1", problem: "P" });
    for (const p of Object.values(ws.paths)) expect(existsSync(p)).toBe(true);
    expect(readFileSync(join(ws.paths.problem, "problem.md"), "utf-8")).toBe("P");
  });
  it("modelDirName('Model 1') === 'model_1'", () => expect(modelDirName("Model 1")).toBe("model_1"));
  it("E2 回归：resume 模式不删除已有 master_plan.md", () => {
    const r = root();
    const ws = prepareWorkspace({ root: r, sessionId: "s2", problem: "P" });
    const plan = join(ws.paths.modeling, "master_plan.md");
    writeFileSync(plan, "## Model 1: KEEP ME");
    const again = prepareWorkspace({ root: r, sessionId: "s2", mode: "resume" });
    expect(readFileSync(join(again.paths.modeling, "master_plan.md"), "utf-8")).toBe("## Model 1: KEEP ME");
  });
  it("ingestData 支持单文件 / 目录 / zip", async () => {
    const ws = prepareWorkspace({ root: root(), sessionId: "s3" });
    const f = join(root(), "a.csv"); writeFileSync(f, "a,b\n1,2\n");
    const d = join(root(), "dset"); mkdirSync(d); writeFileSync(join(d, "b.csv"), "x\n1\n");
    const zip = join(root(), "bundle.zip");
    const JSZip = (await import("jszip")).default;
    const z = new JSZip(); z.file("inner/c.csv", "c\n3\n");
    writeFileSync(zip, await z.generateAsync({ type: "nodebuffer" }));
    const written = await ingestData(ws, [f, d, zip]);
    expect(written.length).toBe(3);
    expect(existsSync(join(ws.paths.data, "a.csv"))).toBe(true);
    expect(existsSync(join(ws.paths.data, "dset/b.csv"))).toBe(true);
    // zip 内单目录自动提升
    expect(existsSync(join(ws.paths.data, "c.csv"))).toBe(true);
  });
  it("zip/unzip 往返还原 + listSessions 倒序 + 真实产物树", async () => {
    const r = root();
    const a = prepareWorkspace({ root: r, sessionId: "older", problem: "A" });
    writeSessionMeta(a, { created_at: "2020-01-01T00:00:00.000Z", status: "completed" });
    const b = prepareWorkspace({ root: r, sessionId: "newer", problem: "B" });
    writeSessionMeta(b, { created_at: "2026-01-01T00:00:00.000Z" });
    writeFileSync(join(b.paths.paper, "main.tex"), "tex");
    expect(listSessions(r).map((x) => x.id)).toEqual(["newer", "older"]);
    const buf = await zipWorkspace(b);
    const dest = root();
    const names = await unzipWorkspace(buf, dest);
    expect(names).toContain("04_paper/main.tex");
    expect(readFileSync(join(dest, "04_paper/main.tex"), "utf-8")).toBe("tex");
    expect(scanArtifacts(b).some((x) => x.path === "04_paper/main.tex")).toBe(true);
  });
});
