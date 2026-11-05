import { spawn } from "node:child_process";
import { Object as TObject, String as TString } from "typebox";

/** 旧提示词依赖「每次调用自带 import + 计算 + print、变量不持久」语义：
 *  spawn 新进程 1:1 复现（T3.3）。 */
export function runPython(code: string, opts: { cwd: string; signal?: AbortSignal; timeoutMs?: number }): Promise<string> {
  return new Promise((resolve, reject) => {
    const p = spawn("python3", ["-c", code], {
      cwd: opts.cwd, signal: opts.signal, timeout: opts.timeoutMs ?? 120_000,
    });
    let out = "", err = "";
    p.stdout.on("data", (d) => { out += String(d); });
    p.stderr.on("data", (d) => { err += String(d); });
    p.on("error", reject);
    p.on("close", (c) => c === 0 ? resolve(out) : reject(new Error(err || `python exited ${c}`)));
  });
}

/** 纯函数：路径逃逸检测（R5），便于单测。 */
export function hasPathEscape(input: unknown): boolean {
  if (!input || typeof input !== "object") return false;
  const o = input as any;
  const paths = [o.path, o.file_path, o.filePath, o.target_file, o.filename, o.destination]
    .filter((v): v is string => typeof v === "string");
  return paths.some((p) => {
    const normalized = p.replace(/\\/g, "/");
    return normalized.split("/").includes("..") || /^[A-Za-z]:\//.test(normalized);
  });
}

const WRITE_TOOLS = new Set(["write", "edit", "str_replace_editor"]);

/** tool_call 拦截：路径逃逸 + 并行 writablePrefixes 越界（R11）。 */
export function safetyExtension(pi: any, writablePrefixes?: string[]): void {
  pi.on("tool_call", async (event: any) => {
    if (hasPathEscape(event?.input)) return { block: true, reason: "Path escapes workspace" };
    if (writablePrefixes?.length && WRITE_TOOLS.has(event?.toolName)) {
      const p = String(event?.input?.path ?? event?.input?.file_path ?? "").replace(/\\/g, "/");
      if (p && !writablePrefixes.some((pref) => p.startsWith(pref.replace(/\\/g, "/"))))
        return { block: true, reason: `Write outside allowed prefixes: ${p}` };
    }
    return undefined;
  });
}

/** 自定义工具（createAgentSession({ customTools })）。 */
export function buildCustomTools(): any[] {
  return [
    {
      name: "python_execute", label: "Run Python",
      description: "Execute Python code in a fresh process. Variables do NOT persist between calls; include imports, computation and print() in one call.",
      parameters: TObject({ code: TString({ description: "Complete Python snippet" }) }),
      async execute(_id: string, params: any, signal: AbortSignal | undefined, _onUpdate: any, ctx: any) {
        try {
          const out = await runPython(params.code, { cwd: ctx.cwd, signal, timeoutMs: 120_000 });
          return { content: [{ type: "text", text: out }], details: {} };
        } catch (e) {
          return { content: [{ type: "text", text: String(e) }], details: {}, isError: true };
        }
      },
    },
    {
      name: "arxiv_search", label: "ArXiv Search",
      description: "Search ArXiv for academic papers on mathematical modeling methods.",
      parameters: TObject({ query: TString({ description: "Search query" }) }),
      async execute(_id: string, params: any) {
        return { content: [{ type: "text", text: `ArXiv search placeholder for: ${params.query}. Configure MCP for live results.` }], details: {} };
      },
    },
    {
      name: "web_search", label: "Web Search",
      description: "Search the web for tutorials, blog posts, and practical solutions.",
      parameters: TObject({ query: TString({ description: "Search query" }) }),
      async execute(_id: string, params: any) {
        return { content: [{ type: "text", text: `Web search placeholder for: ${params.query}. Configure MCP for live results.` }], details: {} };
      },
    },
    {
      name: "webReader", label: "Read URL",
      description: "Read and extract content from any URL.",
      parameters: TObject({ url: TString({ description: "URL" }) }),
      async execute(_id: string, params: any) {
        return { content: [{ type: "text", text: `URL reader placeholder for: ${params.url}. Configure MCP for live results.` }], details: {} };
      },
    },
  ];
}
