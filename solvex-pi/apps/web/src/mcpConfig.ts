import type { FastifyInstance } from "fastify";
import {
  loadMcpConfig, saveMcpConfig, getSharedMcpManager, resetSharedMcpManager,
  resolveMcpConfigPath, missingEnvRefs, MCP_SEARCH_PRESETS, findMcpPreset, applyMcpPreset,
} from "@solvex/pi-runtime";

/**
 * WebUI 的 MCP 配置入口。GET 只回显 `$VAR` 引用与 tools/list 发现的真实工具，
 * 绝不回显任何明文凭据（ADR-0007 / ADR-0012）。
 */
export class McpService {
  constructor(private readonly configPath?: string) {}
  get path(): string { return resolveMcpConfigPath(this.configPath); }

  private mgr() {
    return getSharedMcpManager({ cwd: process.cwd(), configPath: this.configPath });
  }

  async status() {
    const loaded = loadMcpConfig(this.configPath);
    await this.mgr().ready();
    return {
      path: loaded.path,
      config: loaded.config,
      errors: loaded.errors,
      servers: this.mgr().status(),
    };
  }

  async save(raw: unknown) {
    const v = saveMcpConfig(raw, this.configPath);
    if (!v.ok) throw new Error(v.errors.join("; "));
    await resetSharedMcpManager({ cwd: process.cwd(), configPath: this.configPath });
    return this.status();
  }

  async refresh() {
    await resetSharedMcpManager({ cwd: process.cwd(), configPath: this.configPath });
    return this.status();
  }

  /** 内置预设目录：附带「是否已启用」和「缺哪些环境变量」的实时状态。 */
  presets() {
    const current = loadMcpConfig(this.configPath).config;
    return MCP_SEARCH_PRESETS.map((p) => ({
      id: p.id, name: p.name, summary: p.summary, requiresKey: p.requiresKey,
      envVars: p.envVars, serverName: p.serverName, docsUrl: p.docsUrl, note: p.note,
      enabled: Boolean(current.mcpServers?.[p.serverName]),
      missingEnv: missingEnvRefs(p.config),
    }));
  }

  /** 一键启用：合并进现有 mcp.json（不覆盖同名 server），保存后重连。 */
  async applyPreset(id: string) {
    if (!findMcpPreset(id)) throw new Error(`未知的 MCP 预设: ${id}`);
    const v = saveMcpConfig(applyMcpPreset(loadMcpConfig(this.configPath).config, id), this.configPath);
    if (!v.ok) throw new Error(v.errors.join("; "));
    await resetSharedMcpManager({ cwd: process.cwd(), configPath: this.configPath });
    return this.status();
  }
}

export function registerMcpRoutes(app: FastifyInstance, service: McpService): void {
  app.get("/api/mcp", async () => service.status());
  app.put("/api/mcp", async (req, reply) => {
    try { return await service.save(req.body); }
    catch (e: any) { return reply.code(400).send({ error: e.message }); }
  });
  app.post("/api/mcp/refresh", async () => service.refresh());
  app.get("/api/mcp/path", async () => ({ path: service.path }));
  app.get("/api/mcp/presets", async () => ({ presets: service.presets() }));
  app.post<{ Params: { id: string } }>("/api/mcp/presets/:id", async (req, reply) => {
    try { return await service.applyPreset(req.params.id); }
    catch (e: any) { return reply.code(400).send({ error: e.message }); }
  });
}
