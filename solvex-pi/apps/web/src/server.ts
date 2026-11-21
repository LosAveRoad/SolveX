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
import { registerMcpRoutes, McpService } from "./mcpConfig.js";
import { registerSse } from "./sse.js";
import { WorkspaceStore, registerWorkspaceRoutes } from "./workspaces.js";
import { loadSolvexEnv } from "@solvex/pi-runtime";

export type ServerOptions = {
  port?: number;
  sessionRoot?: string;
  workspaceRoot?: string;
  configPath?: string;
  modelsPath?: string;
  mcpConfigPath?: string;
  pingMs?: number;
  logger?: boolean;
};

const DEFAULT_ROOT = join(homedir(), ".solvex", "sessions");
const DIST_DIR = fileURLToPath(new URL("../dist/", import.meta.url));
const PUBLIC_DIR = fileURLToPath(new URL("../public/", import.meta.url));

export async function createServer(opts: ServerOptions = {}) {
  // 直接以库方式启动（测试 / 嵌入式）也要能读到项目根 .env；幂等且不覆盖已 export 的变量。
  loadSolvexEnv();
  const app = Fastify({ logger: opts.logger ?? false, bodyLimit: 64 * 1024 * 1024 });
  await app.register(multipart, { limits: { fileSize: 50 * 1024 * 1024, files: 30, fields: 20, fieldSize: 8 * 1024 * 1024 } });
  await app.register(fastifyStatic, { root: PUBLIC_DIR, prefix: "/static/" });

  const sessionRoot = opts.sessionRoot ?? DEFAULT_ROOT;
  const workspaceRoot = opts.workspaceRoot ?? join(dirname(sessionRoot), "workspaces");
  const registry = new SessionRegistry({ sessionRoot, workspaceRoot,
    configPath: opts.configPath, modelsPath: opts.modelsPath,
    mcpConfigPath: opts.mcpConfigPath });
  const modelConfig = new ModelConfigService({ configPath: opts.configPath, modelsPath: opts.modelsPath });
  registerRoutes(app, { registry, modelConfig });
  registerMcpRoutes(app, new McpService(opts.mcpConfigPath));
  registerWorkspaceRoutes(app, new WorkspaceStore(workspaceRoot), registry);
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
