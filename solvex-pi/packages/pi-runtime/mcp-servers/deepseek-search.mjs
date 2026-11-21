#!/usr/bin/env node
/**
 * SolveX 内置 MCP server：把 DeepSeek 官方 Search / Fetch REST API 包装成标准 MCP 工具。
 *
 * 通过 stdio 上的换行分隔 JSON-RPC 与 pi-mcp 客户端通信。stdout 只输出 JSON-RPC，
 * 任何日志一律走 stderr，否则会破坏协议流。
 *
 * 官方端点（2026-10-17 上线）：
 *   POST https://api.deepseek.com/v1/tools/search  { query, count, need_content, ... }
 *   POST https://api.deepseek.com/v1/tools/fetch   { url }
 * 鉴权：Authorization: Bearer $DEEPSEEK_API_KEY；Search / Fetch 各按成功请求计费
 * （¥5/1000 次，失败 / 无结果 / 超时不计费）；账号级限速 Search 100 QPS / Fetch 25 QPS
 * （2026-11-09 按官方文档核对）。
 *
 * DEEPSEEK_API_BASE_URL 仅用于本地端到端测试（指向假 server），生产不要设置。
 */
import { createInterface } from "node:readline";

const BASE = (process.env.DEEPSEEK_API_BASE_URL || "https://api.deepseek.com/v1/tools").replace(/\/$/, "");
const KEY = process.env.DEEPSEEK_API_KEY || "";

const TOOLS = [
  {
    name: "deepseek_search",
    description: "Search the web with DeepSeek's own search engine. Returns ranked titles, URLs, dates, authority scores and model-ready summaries. Supports site:, -site:, quoted phrases, lang:, after:, before: operators.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query, 1-128 characters" },
        count: { type: "integer", minimum: 1, maximum: 50, description: "Number of results, default 10" },
        need_content: { type: "boolean", description: "Include page content in each result" },
      },
      required: ["query"],
    },
  },
  {
    name: "deepseek_fetch",
    description: "Fetch a single web page and return its title and Markdown body text via DeepSeek Fetch API.",
    inputSchema: {
      type: "object",
      properties: { url: { type: "string", description: "HTTP/HTTPS URL, at most 8192 characters" } },
      required: ["url"],
    },
  },
];

const send = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");
const log = (...parts) => process.stderr.write(`[solvex-deepseek-mcp] ${parts.join(" ")}\n`);

async function api(path, body) {
  if (!KEY) throw new Error("DEEPSEEK_API_KEY is not set; export it before starting SolveX");
  const res = await fetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${KEY}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const raw = await res.text();
  if (!res.ok) throw new Error(`DeepSeek ${path} HTTP ${res.status}: ${raw.slice(0, 300)}`);
  try { return JSON.parse(raw); }
  catch { throw new Error(`DeepSeek ${path} returned non-JSON: ${raw.slice(0, 200)}`); }
}

const clampCount = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(50, Math.max(1, Math.round(n))) : 10;
};

function formatSearch(data) {
  const results = Array.isArray(data?.results) ? data.results : [];
  if (!results.length) return "No results found for this query.";
  return results.map((r, i) => [
    `${i + 1}. ${r.title ?? "(untitled)"}`,
    `   URL: ${r.url ?? ""}`,
    r.date ? `   Date: ${r.date}` : null,
    typeof r.authority === "number" ? `   Authority: ${r.authority}/4` : null,
    `   ${String(r.summary ?? r.snippet ?? r.content ?? "").trim()}`,
  ].filter(Boolean).join("\n")).join("\n\n");
}

async function handle(msg) {
  const { id, method, params } = msg;
  if (method === "initialize") {
    return { jsonrpc: "2.0", id, result: {
      protocolVersion: params?.protocolVersion ?? "2025-06-18",
      capabilities: { tools: {} },
      serverInfo: { name: "solvex-deepseek-search", version: "2.1.3" },
    } };
  }
  if (method === "tools/list") return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
  if (method === "ping") return { jsonrpc: "2.0", id, result: {} };
  if (method === "tools/call") {
    const name = params?.name;
    const args = params?.arguments ?? {};
    try {
      let text;
      if (name === "deepseek_search") {
        text = formatSearch(await api("search", {
          query: String(args.query ?? "").slice(0, 128),
          count: clampCount(args.count),
          ...(args.need_content ? { need_content: true } : {}),
        }));
      } else if (name === "deepseek_fetch") {
        const data = await api("fetch", { url: String(args.url ?? "").slice(0, 8192) });
        text = `# ${data.title ?? "(untitled)"}\n\n${data.content ?? ""}`;
      } else {
        throw new Error(`Unknown tool: ${name}`);
      }
      return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text }], isError: false } };
    } catch (e) {
      return { jsonrpc: "2.0", id, result: {
        content: [{ type: "text", text: `DeepSeek MCP error: ${String(e?.message ?? e)}` }], isError: true,
      } };
    }
  }
  return { jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } };
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { log("ignored non-JSON line"); return; }
  if (msg.id === undefined) return;
  void handle(msg).then(send).catch((e) =>
    send({ jsonrpc: "2.0", id: msg.id, error: { code: -32603, message: String(e?.message ?? e) } }));
});
rl.on("close", () => process.exit(0));
