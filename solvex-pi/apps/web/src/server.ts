import Fastify from "fastify";
import multipart from "@fastify/multipart";
import fastifyStatic from "@fastify/static";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { homedir } from "node:os";
import { SessionRegistry } from "./runner.js";
import { ModelConfigService } from "./modelConfig.js";
import { registerRoutes } from "./routes.js";
import { registerSse } from "./sse.js";

export type ServerOptions = {
  port?: number;
  fake?: boolean;
  sessionRoot?: string;
  configPath?: string;
  modelsPath?: string;
  pingMs?: number;
  logger?: boolean;
};

const DEFAULT_ROOT = join(homedir(), ".solvex", "sessions");
const PUBLIC_DIR = fileURLToPath(new URL("../public/", import.meta.url));

export async function createServer(opts: ServerOptions = {}) {
  const app = Fastify({ logger: opts.logger ?? false, bodyLimit: 64 * 1024 * 1024 });
  await app.register(multipart, { limits: { fileSize: 50 * 1024 * 1024 } });
  await app.register(fastifyStatic, { root: PUBLIC_DIR, prefix: "/static/" });

  const registry = new SessionRegistry({ fake: opts.fake, sessionRoot: opts.sessionRoot ?? DEFAULT_ROOT,
    configPath: opts.configPath, modelsPath: opts.modelsPath });
  const modelConfig = new ModelConfigService({ configPath: opts.configPath, modelsPath: opts.modelsPath });
  registerRoutes(app, { registry, modelConfig });
  registerSse(app, registry, opts.pingMs ?? 30_000);

  app.get("/", (_req, reply) => reply.sendFile("index.html"));
  return app;
}

export async function startServer(opts: ServerOptions = {}) {
  const app = await createServer(opts);
  // 只绑定 127.0.0.1（R5 / ADR-10）
  await app.listen({ host: "127.0.0.1", port: opts.port ?? 8000 });
  return app;
}
