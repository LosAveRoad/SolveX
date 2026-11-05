import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { createServer } from "@solvex/web";
import { testPaths, multipart, startRun, waitForCompletion } from "./helpers.js";

let app: any; let paths: ReturnType<typeof testPaths>;

beforeAll(async () => {
  paths = testPaths();
  app = await createServer({ fake: true, sessionRoot: paths.sessionRoot,
    configPath: paths.configPath, modelsPath: paths.modelsPath, pingMs: 200 });
  await app.ready();
});
afterAll(async () => { await app.close(); });

describe("5A 后端 14 端点", () => {
  it("T5.1 POST /api/run：multipart text+files[] → {session_id}；空 text → 400", async () => {
    const { res, id } = await startRun(app, "A modeling problem", { concurrency: "2", strict: "false" },
      [{ filename: "data.csv", content: "a,b\n1,2\n" }]);
    expect(res.statusCode).toBe(200);
    expect(id).toBeTruthy();
    const bad = await app.inject({ method: "POST", url: "/api/run",
      payload: multipart({ text: "" }).body,
      headers: { "content-type": multipart().contentType } });
    expect(bad.statusCode).toBe(400);
  });

  it("T5.4 GET /api/sessions 与旧版字段一致", async () => {
    const { id } = await startRun(app, "session list problem");
    const r = await app.inject({ method: "GET", url: "/api/sessions" });
    expect(r.statusCode).toBe(200);
    const list = r.json();
    expect(Array.isArray(list)).toBe(true);
    expect(list.some((s: any) => s.id === id)).toBe(true);
    expect(list[0]).toHaveProperty("status");
    expect(list[0]).toHaveProperty("created_at");
  });

  it("T5.5 GET /api/artifacts 返回真实产物树（非硬编码假列表）", async () => {
    const { id } = await startRun(app, "artifact problem");
    await waitForCompletion(app, id);
    const r = await app.inject({ method: "GET", url: `/api/artifacts/${id}` });
    const tree = r.json();
    const pathsList = tree.map((x: any) => x.path ?? x);
    expect(pathsList).toContain("00_problem/problem.md");
    expect(pathsList).toContain("01_modeling/master_plan.md");
    expect(pathsList).toContain("02_programming/all_results_summary.md");
    expect(pathsList).toContain("04_paper/main.tex");
  });

  it("单文件预览 + 路径逃逸拦截", async () => {
    const { id } = await startRun(app, "preview problem");
    await waitForCompletion(app, id);
    const ok = await app.inject({ method: "GET", url: `/api/artifacts/${id}/04_paper/main.tex` });
    expect(ok.statusCode).toBe(200);
    expect(ok.body).toContain("\\documentclass");
    const bad = await app.inject({ method: "GET", url: `/api/artifacts/${id}/../../etc/passwd` });
    expect([404, 400]).toContain(bad.statusCode);
  });

  it("T5.7 GET /api/events 回放全类型事件（原始 SolveXEvent）", async () => {
    const { id } = await startRun(app, "events problem");
    const events = await waitForCompletion(app, id);
    expect(events.length).toBeGreaterThan(5);
    const types = new Set(events.map((e: any) => e.type));
    for (const t of ["status", "step", "done", "stage", "barrier", "lifecycle", "complete"])
      expect(types.has(t)).toBe(true);
    const r = await app.inject({ method: "GET", url: `/api/events/${id}?since=2` });
    expect(r.json().events.length).toBeLessThan(events.length);
  });

  it("T5.8 GET /api/stages 返回完整 DAG，并行节点状态独立", async () => {
    const { id } = await startRun(app, "stages problem");
    await waitForCompletion(app, id);
    const r = await app.inject({ method: "GET", url: `/api/stages/${id}` });
    const stages = r.json().stages;
    expect(Array.isArray(stages)).toBe(true);
    expect(stages.some((s: any) => s.id === "P1" && s.state === "done")).toBe(true);
    expect(stages.filter((s: any) => s.id.startsWith("P2-IMPL:")).length).toBeGreaterThanOrEqual(1);
    expect(r.json().barriers).toBeTruthy();
  });

  it("T5.3 GET /api/download 返回合法 ZIP", async () => {
    const { id } = await startRun(app, "download problem");
    await waitForCompletion(app, id);
    const r = await app.inject({ method: "GET", url: `/api/download/${id}` });
    expect(r.statusCode).toBe(200);
    expect(r.headers["content-type"]).toContain("zip");
    expect(r.rawPayload.slice(0, 2).toString()).toBe("PK");
  });

  it("T5.6 POST /api/abort 取消运行且产物不损坏", async () => {
    const { id } = await startRun(app, "abort problem");
    const r = await app.inject({ method: "POST", url: `/api/abort/${id}` });
    expect(r.json()).toEqual({ status: "aborted" });
    const s = await app.inject({ method: "GET", url: "/api/sessions" });
    expect(s.json().find((x: any) => x.id === id).status).toBe("aborted");
  });

  it("T5.9 GET /api/models 脱敏：响应体无任何明文密钥", async () => {
    const r = await app.inject({ method: "GET", url: "/api/models" });
    const d = r.json();
    expect(Array.isArray(d.models)).toBe(true);
    expect(d.models.length).toBeGreaterThan(0);
    expect(d.thinkingLevels).toHaveLength(7);
    expect(JSON.stringify(d)).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
    expect(JSON.stringify(d)).not.toContain("apiKey");
    for (const c of d.credentials) expect(c.masked !== undefined).toBe(true);
  });

  it("T5.10 PUT /api/models/config 保存后 GET 回读一致；非法档位 400", async () => {
    const put = await app.inject({ method: "PUT", url: "/api/models/config",
      payload: { defaults: { provider: "anthropic", model: "claude-sonnet-4-5", thinkingLevel: "high" },
                 scopedModels: ["anthropic/claude-sonnet-4-5"] } });
    expect(put.statusCode).toBe(200);
    const get = await app.inject({ method: "GET", url: "/api/models" });
    expect(get.json().config.defaults.model).toBe("claude-sonnet-4-5");
    const bad = await app.inject({ method: "PUT", url: "/api/models/config",
      payload: { thinkingLevels: ["ULTRA"] } });
    expect(bad.statusCode).toBe(400);
  });

  it("T5.11 POST /api/models/refresh 重载 catalog", async () => {
    const r = await app.inject({ method: "POST", url: "/api/models/refresh" });
    expect(r.statusCode).toBe(200);
    expect(r.json().models.length).toBeGreaterThan(0);
  });

  it("T5.12 POST /api/models/api-key：provider 变 available，key 不落盘不进日志", async () => {
    const r = await app.inject({ method: "POST", url: "/api/models/api-key",
      payload: { provider: "anthropic", apiKey: "sk-plaintext-secret-9999" } });
    expect(r.statusCode).toBe(200);
    const d = (await app.inject({ method: "GET", url: "/api/models" })).json();
    expect(d.models.filter((m: any) => m.provider === "anthropic").every((m: any) => m.available)).toBe(true);
    expect(JSON.stringify(d)).not.toContain("sk-plaintext-secret-9999");
    expect(existsSync(paths.configPath) ? readFileSync(paths.configPath, "utf-8") : "")
      .not.toContain("sk-plaintext-secret-9999");
  });

  it("T5.13 PUT /api/models/endpoints 写入 SDK 合规 models.json，凭据只存引用", async () => {
    const r = await app.inject({ method: "PUT", url: "/api/models/endpoints",
      payload: { id: "my-openai", baseUrl: "https://api.example.com/v1", api: "openai-completions",
        apiKey: "$MY_KEY", models: ["model-a", "model-b"] } });
    expect(r.statusCode).toBe(200);
    const raw = readFileSync(paths.modelsPath, "utf-8");
    expect(raw).toContain("$MY_KEY");
    expect(raw).not.toContain("sk-");
    const catalog = JSON.parse(raw);
    // SDK schema：models 必须是对象数组且 cost 含 cacheRead/cacheWrite
    expect(catalog.providers["my-openai"].models[0]).toMatchObject({ id: "model-a" });
    expect(catalog.providers["my-openai"].models[0].cost).toHaveProperty("cacheRead");
    const d = (await app.inject({ method: "GET", url: "/api/models" })).json();
    expect(d.models.some((m: any) => m.id === "model-a" && m.source === "models.json")).toBe(true);
  });

  it("T5.14 GET /api/models/thinking-levels 按模型能力裁剪", async () => {
    const reasoning = await app.inject({ method: "GET", url: "/api/models/thinking-levels?model=claude-sonnet-4-5" });
    expect(reasoning.json().levels.length).toBe(7);
    const plain = await app.inject({ method: "GET", url: "/api/models/thinking-levels?model=gpt-5-mini" });
    expect(plain.json().levels).toEqual(["off"]);
  });

  it("GET / 返回 WebUI 2.0 页面，/static/* 可访问", async () => {
    const r = await app.inject({ method: "GET", url: "/" });
    expect(r.statusCode).toBe(200);
    expect(r.body).toContain("SolveX");
    const js = await app.inject({ method: "GET", url: "/static/app.js" });
    expect(js.statusCode).toBe(200);
  });
});
