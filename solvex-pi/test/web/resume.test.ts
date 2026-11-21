import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createServer } from "@solvex/web";
import { testPaths, startRun, waitForCompletion, installFakeRunner } from "./helpers.js";

let app: any; let paths: ReturnType<typeof testPaths>;

beforeAll(async () => {
  installFakeRunner({ delayMs: 20 });
  paths = testPaths();
  app = await createServer({ sessionRoot: paths.sessionRoot,
    configPath: paths.configPath, modelsPath: paths.modelsPath, pingMs: 200 });
  await app.ready();
});
afterAll(async () => { await app.close(); });

describe("POST /api/resume/:id —— 断点续跑", () => {
  it("中止后续跑：沿用首次的题面与数据说明，跑到完成", async () => {
    const { id } = await startRun(app, "resume problem", {}, [{ filename: "d.csv", content: "a\n1\n" }]);
    await new Promise((r) => setTimeout(r, 30));
    await app.inject({ method: "POST", url: `/api/abort/${id}` });
    const r = await app.inject({ method: "POST", url: `/api/resume/${id}` });
    expect(r.statusCode).toBe(200);
    expect(r.json()).toEqual({ session_id: id, status: "running" });
    const events = await waitForCompletion(app, id, 5000);
    expect(events.some((e: any) => e.type === "complete")).toBe(true);
    const dir = join(paths.sessionRoot, id);
    const meta = JSON.parse(readFileSync(join(dir, ".solvex-meta.json"), "utf-8"));
    expect(meta.dataInfo).toContain("d.csv");
    expect(meta.status).toBe("completed");
    expect(existsSync(join(dir, "04_paper", "main.tex"))).toBe(true);
    // 会话日志不出现在产物树里
    const arts = (await app.inject({ method: "GET", url: `/api/artifacts/${id}` })).json();
    expect(JSON.stringify(arts)).not.toContain(".solvex/journal");
  });
  it("运行中的 run 拒绝续跑（409），不存在的 run 返回 404", async () => {
    const { id } = await startRun(app, "busy problem");
    const busy = await app.inject({ method: "POST", url: `/api/resume/${id}` });
    expect(busy.statusCode).toBe(409);
    const missing = await app.inject({ method: "POST", url: "/api/resume/nope-123" });
    expect(missing.statusCode).toBe(404);
    await waitForCompletion(app, id, 5000);
  });
});
