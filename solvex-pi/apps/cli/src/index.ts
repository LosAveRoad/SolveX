import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import {
  prepareWorkspace, ingestData, scanArtifacts, writeSessionMeta, EventBus, META_FILE,
  SolveXFlow, validateModelOutput,
  type AgentRunner, type ModelConfig,
} from "@solvex/core";
import { PiAgentRunner, ConfigStore, sharedModelRuntime, loadSolvexEnv,
         loadMcpConfig, saveMcpConfig, findMcpPreset, applyMcpPreset,
         missingEnvRefs, MCP_SEARCH_PRESETS } from "@solvex/pi-runtime";
import { parseArgs, HELP, type CliArgs } from "./args.js";
import { renderEvent } from "./renderer.js";

const SESSION_ROOT = join(homedir(), ".solvex", "sessions");

async function readProblem(a: CliArgs): Promise<string> {
  if (a.problem) {
    if (!existsSync(a.problem)) throw new Error(`problem file not found: ${a.problem}`);
    return readFileSync(a.problem, "utf-8");
  }
  if (a.resume) {
    const p = join(a.sessionDir ?? SESSION_ROOT, a.resume, "00_problem", "problem.md");
    if (!existsSync(p)) throw new Error(`no problem.md for session ${a.resume}`);
    return readFileSync(p, "utf-8");
  }
  // 交互式
  process.stdout.write("请输入问题（单行，Ctrl+D 结束）:\n> ");
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf-8").trim();
}

/** 生产路径永远构造真实 runner。FakeAgentRunner 只由内部测试通过依赖注入使用。 */
async function makeRunner(bus: EventBus, mcpConfigPath?: string): Promise<AgentRunner> {
  // 注入 modelRuntime，让 models.json 自定义端点与 config.json 分档模型真正生效
  const modelRuntime = await sharedModelRuntime();
  return new PiAgentRunner({ bus, ...(modelRuntime ? { modelRuntime } : {}),
    ...(mcpConfigPath ? { mcpConfigPath } : {}) });
}

/** --mcp-preset：把内置搜索预设合并进 mcp.json（已启用则跳过，幂等），之后仍走同一套发现链。 */
function enableMcpPreset(a: CliArgs): void {
  if (!a.mcpPreset) return;
  const preset = findMcpPreset(a.mcpPreset);
  if (!preset) throw new Error(`未知的 MCP 预设: ${a.mcpPreset}；可用：${MCP_SEARCH_PRESETS.map(p => p.id).join(", ")}`);
  const current = loadMcpConfig(a.mcpConfig).config;
  if (current.mcpServers?.[preset.serverName]) return;
  const v = saveMcpConfig(applyMcpPreset(current, a.mcpPreset), a.mcpConfig);
  if (!v.ok) throw new Error(v.errors.join("; "));
  process.stdout.write(`MCP 预设已启用: ${preset.name} (${preset.serverName})\n`);
  const missing = missingEnvRefs(preset.config);
  if (missing.length) process.stdout.write(`请先 export 环境变量: ${missing.join(", ")}\n`);
}

async function runCommand(a: CliArgs): Promise<number> {
  enableMcpPreset(a);
  const root = a.sessionDir ?? SESSION_ROOT;
  const problem = await readProblem(a);
  if (!problem) { process.stderr.write("问题文本为空\n"); return 1; }
  const ws = a.resume
    ? prepareWorkspace({ root, sessionId: a.resume, mode: "resume" })
    : prepareWorkspace({ root, problem });
  if (a.data.length) await ingestData(ws, a.data);
  // 续跑沿用首次运行的数据说明（中断前后发给 Agent 的 prompt 必须一致）。
  const metaPath = join(ws.dir, META_FILE);
  const meta = existsSync(metaPath) ? JSON.parse(readFileSync(metaPath, "utf-8")) : {};
  const dataInfo: string = a.data.length ? `\nDATA FILES: ${a.data.join(", ")}\n` : meta.dataInfo ?? "";
  if (!a.resume || a.data.length) writeSessionMeta(ws, { dataInfo });

  const bus = new EventBus();
  bus.subscribe((e) => { const s = renderEvent(e); if (s) process.stdout.write(s + "\n"); });
  const store = new ConfigStore();
  const config: ModelConfig = { ...store.load(), concurrency: a.concurrency, strict: a.strict };
  const flow = new SolveXFlow({ runner: await makeRunner(bus, a.mcpConfig), bus, ws, config, problem,
    dataInfo, skipToWriting: a.skipToWriting });
  const summary = await flow.run();
  process.stdout.write(`\nsession: ${ws.id}\nworkspace: ${ws.dir}\n`);
  return summary.status === "completed" ? 0 : 1;
}

async function inspectCommand(a: CliArgs): Promise<number> {
  const id = a.sessionId;
  if (!id) { process.stderr.write("用法: solvex inspect <session_id>\n"); return 1; }
  const dir = join(a.sessionDir ?? SESSION_ROOT, id);
  if (!existsSync(dir)) { process.stderr.write(`session 不存在: ${id}\n`); return 1; }
  process.stdout.write(`Session ${id}\n产物:\n`);
  for (const f of scanArtifacts({ id, root: a.sessionDir ?? SESSION_ROOT, dir,
    paths: { problem: "", data: "", modeling: "", programming: "", paper: "" } } as any))
    process.stdout.write(`  ${f.isDir ? "📁" : "📄"} ${f.path}${f.isDir ? "" : ` (${f.size}B)`}\n`);
  return 0;
}

async function validateCommand(a: CliArgs): Promise<number> {
  const id = a.sessionId;
  if (!id) { process.stderr.write("用法: solvex validate <session_id>\n"); return 1; }
  const prog = join(a.sessionDir ?? SESSION_ROOT, id, "02_programming");
  if (!existsSync(prog)) { process.stderr.write(`session 不存在: ${id}\n`); return 1; }
  let total = 0;
  for (const d of readdirSync(prog)) {
    const dir = join(prog, d);
    if (!existsSync(join(dir, "results_summary.md"))) continue;
    const issues = validateModelOutput(dir);
    total += issues.length;
    process.stdout.write(`${d}: ${issues.length ? issues.map((i) => i.code).join(", ") : "OK"}\n`);
  }
  process.stdout.write(`共 ${total} 个问题（只读检查，未修改任何产物）\n`);
  return 0;
}

async function serveCommand(a: CliArgs): Promise<number> {
  enableMcpPreset(a);
  const { startServer } = await import("@solvex/web");
  await startServer({ port: a.port, sessionRoot: a.sessionDir ?? SESSION_ROOT,
    ...(a.mcpConfig ? { mcpConfigPath: a.mcpConfig } : {}) });
  process.stdout.write(`SolveX WebUI 2.0: http://127.0.0.1:${a.port}/\n`);
  return 0; // 常驻进程
}

async function main(): Promise<void> {
  loadSolvexEnv(); // 项目根 .env 最先加载，之后所有 $VAR 引用才能解析到真实值
  const a = parseArgs(process.argv.slice(2));
  if (a.help) { process.stdout.write(HELP); return; }
  let code = 0;
  switch (a.command) {
    case "run": code = await runCommand(a); break;
    case "serve": code = await serveCommand(a); break;
    case "inspect": code = await inspectCommand(a); break;
    case "validate": code = await validateCommand(a); break;
    default: process.stdout.write(HELP);
  }
  if (a.command !== "serve") process.exitCode = code;
}

main().catch((e) => { process.stderr.write(`\x1b[1;31m${e?.stack ?? e}\x1b[0m\n`); process.exitCode = 1; });
