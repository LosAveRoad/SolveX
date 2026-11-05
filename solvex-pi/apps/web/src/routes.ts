import { existsSync, readFileSync, statSync } from "node:fs";
import { join, normalize } from "node:path";
import type { FastifyInstance } from "fastify";
import { zipWorkspace } from "@solvex/core";
import type { SessionRegistry } from "./runner.js";
import type { ModelConfigService } from "./modelConfig.js";
import { barrierSnapshot } from "./stages.js";

export type RouteDeps = { registry: SessionRegistry; modelConfig: ModelConfigService };

export function registerRoutes(app: FastifyInstance, deps: RouteDeps): void {
  const { registry, modelConfig } = deps;

  // 1) POST /api/run —— 统一 multipart（同时兼容旧前端误发的 JSON）
  app.post("/api/run", async (req, reply) => {
    const ct = String((req.headers as any)["content-type"] ?? "");
    let text = "", concurrency: number | undefined, strict: boolean | undefined, byPhase: any;
    const files: { filename: string; buffer: Buffer }[] = [];
    if (ct.includes("multipart/form-data")) {
      for await (const part of (req as any).parts()) {
        if (part.type === "file") files.push({ filename: part.filename ?? "upload.bin",
          buffer: await part.toBuffer() });
        else {
          const v = String(part.value ?? "");
          if (part.fieldname === "text") text = v;
          else if (part.fieldname === "concurrency") concurrency = Number(v);
          else if (part.fieldname === "strict") strict = v === "true" || v === "1";
          else if (part.fieldname === "byPhase") { try { byPhase = JSON.parse(v); } catch { /* noop */ } }
        }
      }
    } else {
      const b = (req.body ?? {}) as any;
      text = String(b.text ?? ""); concurrency = b.concurrency; strict = b.strict; byPhase = b.byPhase;
    }
    if (!text.trim()) return reply.code(400).send({ error: "empty text" });
    try {
      const s = await registry.create({ text, files, concurrency, strict, byPhase });
      return reply.code(200).send({ session_id: s.id });
    } catch (e: any) { return reply.code(400).send({ error: e.message }); }
  });

  // 3) GET /api/download/:id
  app.get("/api/download/:id", async (req, reply) => {
    const s = registry.get((req.params as any).id);
    if (!s) return reply.code(404).send({ error: "session not found" });
    const buf = await zipWorkspace(s.ws);
    return reply.header("Content-Type", "application/zip")
      .header("Content-Disposition", `attachment; filename="solvex-${s.id}.zip"`).send(buf);
  });

  // 4) GET /api/sessions —— 正序（前端会反转成新会话在上）
  app.get("/api/sessions", async () => registry.list().slice().reverse());

  // 5) GET /api/artifacts/:id —— 真实产物树（旧版是硬编码假列表）
  app.get("/api/artifacts/:id", async (req, reply) => {
    const s = registry.get((req.params as any).id);
    if (!s) return reply.code(404).send({ error: "session not found" });
    return registry.artifacts(s.id);
  });

  // 5b) GET /api/artifacts/:id/* —— 单文件预览（前端点击文件树时用）
  app.get("/api/artifacts/:id/*", async (req, reply) => {
    const p = req.params as any;
    const s = registry.get(p.id);
    if (!s) return reply.code(404).send({ error: "session not found" });
    const rel = String(p["*"] ?? "");
    const abs = normalize(join(s.ws.dir, rel));
    if (rel.includes("..") || !abs.startsWith(s.ws.dir) || !existsSync(abs) || !statSync(abs).isFile())
      return reply.code(404).send({ error: "artifact not found" });
    return reply.type("text/plain; charset=utf-8").send(readFileSync(abs, "utf-8"));
  });

  // 6) GET /api/events/:id?since=N —— 回放（返回原始 SolveXEvent 数组供前端 reduce）
  app.get("/api/events/:id", async (req) => {
    const q = req.query as any;
    const since = Number(q.since ?? 0);
    const recs = registry.events((req.params as any).id, since);
    return { events: recs.map((r: any) => r.event ?? r), lastSeq: recs.at(-1)?.seq ?? since };
  });

  // 7) GET /api/stages/:id —— 全量 DAG 快照
  app.get("/api/stages/:id", async (req) => {
    const s = registry.get((req.params as any).id);
    return { stages: registry.stages((req.params as any).id),
             barriers: s ? barrierSnapshot(s.bus) : {} };
  });

  // 8) POST /api/abort/:id —— 取消所有在跑并行任务
  app.post("/api/abort/:id", async (req, reply) => {
    const ok = registry.abort((req.params as any).id);
    return ok ? { status: "aborted" } : reply.code(404).send({ error: "session not found" });
  });

  // 9) GET /api/models —— 脱敏（响应体不含任何明文密钥）
  app.get("/api/models", async () => modelConfig.get());

  // 10) PUT /api/models/config
  app.put("/api/models/config", async (req, reply) => {
    try { return modelConfig.save((req.body ?? {}) as any); }
    catch (e: any) { return reply.code(400).send({ error: e.message }); }
  });

  // 11) POST /api/models/refresh
  app.post("/api/models/refresh", async () => { modelConfig.refresh(); return modelConfig.get(); });

  // 12) POST /api/models/api-key —— 只进内存，不落盘不进日志
  app.post("/api/models/api-key", async (req, reply) => {
    const b = (req.body ?? {}) as any;
    if (!b.provider || !b.apiKey) return reply.code(400).send({ error: "provider/apiKey required" });
    modelConfig.setApiKey(String(b.provider), String(b.apiKey));
    return { ok: true, provider: b.provider, masked: "sk-••••" };
  });

  // 13) PUT /api/models/endpoints —— 前端提交单个端点对象
  app.put("/api/models/endpoints", async (req, reply) => {
    const b = (req.body ?? {}) as any;
    const one = Array.isArray(b) ? b : [b];
    const list = one.filter((e) => e?.baseUrl && e?.api).map((e) => ({
      id: String(e.id ?? "custom"), baseUrl: String(e.baseUrl), api: String(e.api),
      apiKey: e.apiKey ? String(e.apiKey) : undefined,
      models: Array.isArray(e.models) ? e.models.map(String) : [],
    }));
    if (!list.length) return reply.code(400).send({ error: "invalid endpoints" });
    modelConfig.setEndpoints(list);
    return modelConfig.get();
  });

  // 14) GET /api/models/thinking-levels?model=
  app.get("/api/models/thinking-levels", async (req) => {
    const model = (req.query as any).model;
    return { levels: modelConfig.thinkingLevels(model ? String(model) : undefined) };
  });
}
