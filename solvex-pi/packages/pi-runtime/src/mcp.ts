import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import {
  McpClient, StdioTransport, StreamableHttpTransport,
  type McpTransport, type Tool as McpTool, type ContentBlock,
} from "@earendil-works/pi-mcp";
import type { Role } from "@solvex/core";
import type { ToolDescriptor } from "@solvex/core";

export const DEFAULT_MCP_CONFIG_PATH = join(homedir(), ".solvex", "mcp.json");
const ROLES: readonly Role[] = ["modeling", "programming", "review", "writing", "visualization"];
const NAME_RE = /^[A-Za-z0-9_-]{1,40}$/;
const ENV_REF = /\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/;
const SENSITIVE = /api[-_]?key|token|secret|authorization|password|credential|bearer/i;
const PLAIN_SECRET = /(?:^|[^$])sk-[A-Za-z0-9_-]{12,}/i;

export type McpServerConfig = {
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  headers?: Record<string, string>;
  cwd?: string;
  description?: string;
  roles?: Role[];
  tools?: string[];
  enabled?: boolean;
  timeoutMs?: number;
};
export type McpConfig = { mcpServers: Record<string, McpServerConfig> };
export type McpValidation = { ok: boolean; errors: string[]; config: McpConfig };

export type NormalizedServer = {
  name: string;
  config: McpServerConfig;
  env: Record<string, string>;
  headers: Record<string, string>;
  roles: Role[];
  allow: Set<string> | undefined;
  timeoutMs: number;
};

/** 把 $VAR / ${VAR} 引用解析成环境变量；缺值时为空串，绝不把引用本身当密钥发出去。 */
export function resolveEnvRef(value: string): string {
  return value.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g,
    (_m, braced: string | undefined, plain: string | undefined) =>
      process.env[braced ?? plain ?? ""] ?? "");
}

const ENV_REF_GLOBAL = /\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g;

/**
 * 找出配置里引用了、但当前进程根本没有设置的环境变量。
 * 是否需要 API key 由 MCP server 决定，SolveX 不判断；这里只做可观测性提示，
 * 避免「server 连上了但 tools/call 才报 401」这种难排查的情况。
 */
export function missingEnvRefs(config: McpServerConfig): string[] {
  const out = new Set<string>();
  for (const bag of [config.env, config.headers]) {
    for (const value of Object.values(bag ?? {})) {
      for (const m of String(value).matchAll(ENV_REF_GLOBAL)) {
        const name = m[1] ?? m[2];
        if (name && !process.env[name]) out.add(name);
      }
    }
  }
  return [...out];
}

/** 纯函数校验：形状、角色白名单、凭据只接受环境变量引用（ADR-0007 同款脱敏口径）。 */
export function validateMcpConfig(raw: unknown): McpValidation {
  const errors: string[] = [];
  const empty: McpConfig = { mcpServers: {} };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ok: false, errors: ["mcp.json 必须是对象"], config: empty };
  const servers = (raw as any).mcpServers;
  if (!servers || typeof servers !== "object" || Array.isArray(servers))
    return { ok: false, errors: ["缺少 mcpServers 对象"], config: empty };

  for (const [name, value] of Object.entries(servers) as [string, any][]) {
    if (!NAME_RE.test(name)) errors.push(`${name}: 服务名只能是 1–40 位字母/数字/下划线/连字符`);
    if (!value || typeof value !== "object" || Array.isArray(value)) { errors.push(`${name}: 配置必须是对象`); continue; }
    const hasCommand = typeof value.command === "string" && value.command.trim().length > 0;
    const hasUrl = typeof value.url === "string" && value.url.trim().length > 0;
    if (hasCommand === hasUrl) errors.push(`${name}: command 与 url 必须且只能提供其一`);
    if (hasUrl && !/^https?:\/\//i.test(String(value.url))) errors.push(`${name}: url 必须是 http(s)://`);
    if (value.args !== undefined && (!Array.isArray(value.args) || value.args.some((a: unknown) => typeof a !== "string")))
      errors.push(`${name}: args 必须是字符串数组`);
    if (value.tools !== undefined && (!Array.isArray(value.tools) || value.tools.some((t: unknown) => typeof t !== "string" || !NAME_RE.test(String(t)))))
      errors.push(`${name}: tools 必须是合法工具名数组`);
    if (value.roles !== undefined && (!Array.isArray(value.roles) || value.roles.some((r: unknown) => !ROLES.includes(r as Role))))
      errors.push(`${name}: roles 只能是 ${ROLES.join(", ")}`);
    for (const field of ["env", "headers"] as const) {
      const bag = value[field];
      if (bag === undefined) continue;
      if (!bag || typeof bag !== "object" || Array.isArray(bag)) { errors.push(`${name}: ${field} 必须是对象`); continue; }
      for (const [k, v] of Object.entries(bag) as [string, unknown][]) {
        if (typeof v !== "string") { errors.push(`${name}: ${field}.${k} 必须是字符串`); continue; }
        if (PLAIN_SECRET.test(v)) errors.push(`${name}: ${field}.${k} 含明文密钥，请使用 $VAR 引用`);
        if (SENSITIVE.test(k) && !ENV_REF.test(v))
          errors.push(`${name}: ${field}.${k} 必须使用 $VAR / \${VAR} 环境变量引用`);
      }
    }
    if (value.timeoutMs !== undefined && (typeof value.timeoutMs !== "number" || value.timeoutMs < 1000 || value.timeoutMs > 300000))
      errors.push(`${name}: timeoutMs 必须在 1000–300000 之间`);
  }
  return { ok: errors.length === 0, errors, config: raw as McpConfig };
}

export function resolveMcpConfigPath(path?: string): string {
  return path ?? process.env.SOLVEX_MCP_CONFIG ?? DEFAULT_MCP_CONFIG_PATH;
}

/** 配置文件缺失时视为「未启用」，不报错、不联网。 */
export function loadMcpConfig(path?: string): { config: McpConfig; errors: string[]; path: string } {
  const p = resolveMcpConfigPath(path);
  if (!existsSync(p)) return { config: { mcpServers: {} }, errors: [], path: p };
  try {
    const v = validateMcpConfig(JSON.parse(readFileSync(p, "utf-8")));
    return { config: v.ok ? v.config : { mcpServers: {} }, errors: v.errors, path: p };
  } catch (e) {
    return { config: { mcpServers: {} }, errors: [`mcp.json 解析失败: ${String(e)}`], path: p };
  }
}

/** 原子写入；保存前必须校验通过。 */
export function saveMcpConfig(raw: unknown, path?: string): McpValidation {
  const v = validateMcpConfig(raw);
  if (!v.ok) return v;
  const p = resolveMcpConfigPath(path);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p + ".tmp", JSON.stringify(v.config, null, 2));
  renameSync(p + ".tmp", p);
  return v;
}

const sanitize = (s: string) => s.replace(/[^A-Za-z0-9_]/g, "_");
function mcpToolName(server: string, tool: string): string {
  const full = `mcp__${sanitize(server)}__${sanitize(tool)}`;
  if (full.length <= 64) return full;
  let h = 5381;
  for (const c of full) h = ((h << 5) + h + c.charCodeAt(0)) >>> 0;
  return `${full.slice(0, 56)}_${h.toString(36).slice(0, 6)}`;
}

function normalize(name: string, config: McpServerConfig): NormalizedServer {
  const env: Record<string, string> = {};
  const headers: Record<string, string> = {};
  for (const [k, v] of Object.entries(config.env ?? {})) env[k] = resolveEnvRef(v);
  for (const [k, v] of Object.entries(config.headers ?? {})) headers[k] = resolveEnvRef(v);
  return {
    name, config, env, headers,
    roles: config.roles?.length ? config.roles : ["modeling"],
    allow: config.tools?.length ? new Set(config.tools) : undefined,
    timeoutMs: config.timeoutMs ?? 30_000,
  };
}

export type McpServerStatus = {
  name: string; state: "connected" | "failed" | "disabled" | "empty";
  description?: string; roles: Role[]; tools: string[];
  /** 配置引用了但进程里没设置的环境变量名（通常是搜索服务的 API key）。 */
  missingEnv?: string[];
  error?: string;
};

type Connection = { server: NormalizedServer; client?: McpClient; tools: McpTool[]; state: McpServerStatus["state"]; error?: string };

/**
 * 一次真实连接 = 一次 tools/list。只有 server 真正返回的工具才会被包装、被发现、被写进提示词，
 * 从根上杜绝 ADR-0008 的「声明了但没接线」幽灵工具。
 */
export class McpManager {
  private readonly connections = new Map<string, Connection>();
  private opening?: Promise<void>;

  constructor(private readonly config: McpConfig,
              private readonly opts: { cwd?: string;
                transportFactory?: (server: NormalizedServer) => McpTransport } = {}) {}

  private makeTransport(s: NormalizedServer): McpTransport {
    if (this.opts.transportFactory) return this.opts.transportFactory(s);
    if (s.config.command)
      return new StdioTransport({ command: s.config.command, args: s.config.args ?? [],
        cwd: s.config.cwd ?? this.opts.cwd, env: s.env, inheritEnv: true, stderr: "pipe" });
    return new StreamableHttpTransport({ url: String(s.config.url), headers: s.headers,
      openGetStream: false });
  }

  async ready(): Promise<void> {
    if (this.opening) return this.opening;
    this.opening = (async () => {
      for (const [name, config] of Object.entries(this.config.mcpServers)) {
        const s = normalize(name, config);
        if (config.enabled === false) {
          this.connections.set(name, { server: s, tools: [], state: "disabled" }); continue;
        }
        const client = new McpClient({ name: "solvex", version: "2.1.2", requestTimeoutMs: s.timeoutMs });
        try {
          await withTimeout(client.connect(this.makeTransport(s)), s.timeoutMs);
          const found = await client.listTools({ timeoutMs: s.timeoutMs });
          const tools = found.filter((t) => !s.allow || s.allow.has(t.name));
          this.connections.set(name, { server: s, client, tools,
            state: tools.length ? "connected" : "empty" });
        } catch (e) {
          await client.close().catch(() => {});
          this.connections.set(name, { server: s, tools: [], state: "failed",
            error: String(e instanceof Error ? e.message : e).slice(0, 300) });
        }
      }
    })();
    return this.opening;
  }

  /** 供代码发现 / 提示词注入使用；描述来自 MCP server 自己的 tools/list。 */
  descriptors(): ToolDescriptor[] {
    const out: ToolDescriptor[] = [];
    for (const c of this.connections.values()) {
      for (const t of c.tools) {
        out.push({ name: mcpToolName(c.server.name, t.name),
          description: (t.description?.trim() || t.title || c.server.config.description
            || `MCP tool ${t.name} from ${c.server.name}`).split("\n")[0].slice(0, 240),
          source: "mcp", roles: c.server.roles, server: c.server.name, toolName: t.name });
      }
    }
    return out;
  }

  /** 包装成 Pi customTools；execute 转发 tools/call，错误与文本都原样回给模型。 */
  customTools(role: Role): any[] {
    const out: any[] = [];
    for (const c of this.connections.values()) {
      if (!c.client || !c.server.roles.includes(role)) continue;
      for (const t of c.tools) {
        const schema = (t.inputSchema ?? {}) as Record<string, unknown>;
        out.push({
          name: mcpToolName(c.server.name, t.name),
          label: `${c.server.name}/${t.name}`,
          description: (t.description?.trim() || t.title || `MCP tool ${t.name}`),
          parameters: { ...schema, type: schema.type ?? "object", properties: schema.properties ?? {} },
          async execute(_id: string, params: any, signal?: AbortSignal) {
            try {
              const r = await c.client!.callTool(t.name, (params ?? {}) as Record<string, unknown>,
                { signal, timeoutMs: c.server.timeoutMs });
              return { content: toPiContent(r.content),
                details: { server: c.server.name, tool: t.name, source: "mcp" },
                isError: Boolean(r.isError) };
            } catch (e) {
              return { content: [{ type: "text", text: `MCP tool error: ${String(e)}` }],
                details: { server: c.server.name, tool: t.name, source: "mcp" }, isError: true };
            }
          },
        });
      }
    }
    return out;
  }

  status(): McpServerStatus[] {
    return [...this.connections.values()].map((c) => {
      const missingEnv = missingEnvRefs(c.server.config);
      return {
        name: c.server.name, state: c.state, description: c.server.config.description,
        roles: c.server.roles,
        tools: c.tools.map((t) => mcpToolName(c.server.name, t.name)),
        ...(missingEnv.length ? { missingEnv } : {}),
        ...(c.error ? { error: c.error } : {}),
      };
    });
  }

  async close(): Promise<void> {
    for (const c of this.connections.values()) await c.client?.close().catch(() => {});
    this.connections.clear();
    this.opening = undefined;
  }
}

/** connect() 自身不带 signal，统一加硬超时，避免不可达的 MCP server 卡住整条流水线。 */
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`MCP connect timed out after ${ms}ms`)), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

function toPiContent(blocks: readonly ContentBlock[] | undefined): any[] {
  return (blocks ?? []).map((b: any) => {
    if (b?.type === "text") return { type: "text", text: String(b.text ?? "") };
    if (b?.type === "image") return { type: "image", data: String(b.data ?? ""), mimeType: String(b.mimeType ?? "image/png") };
    return { type: "text", text: JSON.stringify(b) };
  });
}

/** 按 configPath + cwd 复用连接；上限 8 个，超出关闭最旧的（每个 run 的工作目录不同）。 */
const shared = new Map<string, McpManager>();
export function getSharedMcpManager(opts: { cwd?: string; configPath?: string } = {}): McpManager {
  const path = resolveMcpConfigPath(opts.configPath);
  const key = `${path}|${opts.cwd ?? ""}`;
  const hit = shared.get(key);
  if (hit) return hit;
  const manager = new McpManager(loadMcpConfig(path).config, { cwd: opts.cwd ?? process.cwd() });
  shared.set(key, manager);
  if (shared.size > 8) {
    const [oldestKey, oldest] = shared.entries().next().value as [string, McpManager];
    shared.delete(oldestKey); void oldest.close();
  }
  return manager;
}

/** 配置改动后只重建指定 key 的连接，不影响正在跑的其它工作区 session。 */
export async function resetSharedMcpManager(opts: { cwd?: string; configPath?: string } = {}): Promise<void> {
  const key = `${resolveMcpConfigPath(opts.configPath)}|${opts.cwd ?? ""}`;
  const hit = shared.get(key);
  if (hit) { shared.delete(key); await hit.close(); }
}

export async function resetSharedMcpManagerForTest(): Promise<void> {
  for (const m of shared.values()) await m.close();
  shared.clear();
}
