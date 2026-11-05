import { spawn, spawnSync } from "node:child_process";
import { Object as TObject, String as TString } from "typebox";

/** ADR-0009：Python 绘图依赖缺失时给出可执行的指引，避免模型静默跳过 figures。 */
export const PYTHON_PLOTTING_DEPS: readonly string[] = ["numpy", "pandas", "matplotlib"];

export function checkPythonDeps(deps: readonly string[] = PYTHON_PLOTTING_DEPS): string[] {
  const code = "import importlib.util,json;print(json.dumps(" +
    `[m for m in ${JSON.stringify(deps)} if importlib.util.find_spec(m) is None]))`;
  const r = spawnSync("python3", ["-c", code], { encoding: "utf-8" });
  if (r.status !== 0 || r.error) return [...deps];
  try { return JSON.parse(String(r.stdout).trim()); } catch { return [...deps]; }
}

function withDepHint(message: string): string {
  if (!/ModuleNotFoundError|ImportError/.test(message)) return message;
  const m = message.match(/No module named ['"]([^'"]+)['"]/);
  const pkg = m ? m[1] : "the missing package";
  return `${message}\n[SolveX] Python dependency '${pkg}' is missing in this runtime. ` +
    `Ask the operator to install it (e.g. pip3 install matplotlib), or record the exact ImportError ` +
    `in results_summary.md. Do NOT silently skip figure generation.`;
}

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
    p.on("close", (c) => c === 0 ? resolve(out)
      : reject(new Error(withDepHint(err || `python exited ${c}`))));
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

/**
 * 自定义工具（由 PiAgentRunner 注入 createAgentSession({ customTools })）。
 *
 * ADR-0008：只保留有真实实现的工具。旧 Python 运行时的 arxiv_search /
 * web_search / webReader 曾以 placeholder 形式返回 "...Configure MCP for live
 * results." 的假结果，模型会据此反复检索、或用 bash + curl 自行联网，请求超时后
 * 陷入无限重试。它们已从工具白名单和这里的注册表中一并移除；需要联网检索时应
 * 通过 MCP 单独接入并显式登记到 AVAILABLE_TOOLS。
 */
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
  ];
}
