import Fastify from "fastify";
import { existsSync } from "node:fs";
import multipart from "@fastify/multipart";
import fastifyStatic from "@fastify/static";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { SessionRegistry } from "./runner.js";
import { ModelConfigService } from "./modelConfig.js";
import { registerRoutes } from "./routes.js";
import { registerSse } from "./sse.js";
import { WorkspaceStore, registerWorkspaceRoutes } from "./workspaces.js";

export type ServerOptions = {
  port?: number;
  sessionRoot?: string;
  workspaceRoot?: string;
  configPath?: string;
  modelsPath?: string;
  pingMs?: number;
  logger?: boolean;
};

const DEFAULT_ROOT = join(homedir(), ".solvex", "sessions");
const DIST_DIR = fileURLToPath(new URL("../dist/", import.meta.url));
const PUBLIC_DIR = fileURLToPath(new URL("../public/", import.meta.url));

export async function createServer(opts: ServerOptions = {}) {
  const app = Fastify({ logger: opts.logger ?? false, bodyLimit: 64 * 1024 * 1024 });
  await app.register(multipart, { limits: { fileSize: 50 * 1024 * 1024, files: 30, fields: 20, fieldSize: 8 * 1024 * 1024 } });
  await app.register(fastifyStatic, { root: PUBLIC_DIR, prefix: "/static/" });

  const registry = new SessionRegistry({ sessionRoot: opts.sessionRoot ?? DEFAULT_ROOT,
    configPath: opts.configPath, modelsPath: opts.modelsPath });
  const modelConfig = new ModelConfigService({ configPath: opts.configPath, modelsPath: opts.modelsPath });
  registerRoutes(app, { registry, modelConfig });
  registerWorkspaceRoutes(app, new WorkspaceStore(opts.workspaceRoot ?? join(dirname(opts.sessionRoot ?? DEFAULT_ROOT), "workspaces")), registry);
  registerSse(app, registry, opts.pingMs ?? 30_000);

  if (existsSync(join(DIST_DIR, "index.html"))) {
    await app.register(fastifyStatic, { root: DIST_DIR, prefix: "/ui/", decorateReply: false });
    app.get("/", (_req, reply) => reply.type("text/html").sendFile("index.html", DIST_DIR));
  } else {
    app.get("/", (_req, reply) => reply.type("text/html").send(
      "<!doctype html><html lang=zh-CN><meta charset=utf-8><title>SolveX</title><h1>SolveX</h1><p>请先运行 npm run build:web，然后重新启动 serve。</p></html>"));
  }
  return app;
}

export async function startServer(opts: ServerOptions = {}) {
  const app = await createServer(opts);
  // 只绑定 127.0.0.1（R5 / ADR-10）
  await app.listen({ host: "127.0.0.1", port: opts.port ?? 8000 });
  return app;
}
