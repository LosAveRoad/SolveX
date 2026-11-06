import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import {
  prepareWorkspace, ingestData, scanArtifacts, EventBus,
  SolveXFlow, validateModelOutput,
  type AgentRunner, type ModelConfig,
} from "@solvex/core";
import { PiAgentRunner, ConfigStore, sharedModelRuntime } from "@solvex/pi-runtime";
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
async function makeRunner(bus: EventBus): Promise<AgentRunner> {
  // 注入 modelRuntime，让 models.json 自定义端点与 config.json 分档模型真正生效
  const modelRuntime = await sharedModelRuntime();
  return new PiAgentRunner({ bus, ...(modelRuntime ? { modelRuntime } : {}) });
}

async function runCommand(a: CliArgs): Promise<number> {
  const root = a.sessionDir ?? SESSION_ROOT;
  const problem = await readProblem(a);
  if (!problem) { process.stderr.write("问题文本为空\n"); return 1; }
  const ws = a.resume
    ? prepareWorkspace({ root, sessionId: a.resume, mode: "resume" })
    : prepareWorkspace({ root, problem });
  if (a.data.length) await ingestData(ws, a.data);

  const bus = new EventBus();
  bus.subscribe((e) => { const s = renderEvent(e); if (s) process.stdout.write(s + "\n"); });
  const store = new ConfigStore();
  const config: ModelConfig = { ...store.load(), concurrency: a.concurrency, strict: a.strict };
  const flow = new SolveXFlow({ runner: await makeRunner(bus), bus, ws, config, problem,
    dataInfo: a.data.length ? `\nDATA FILES: ${a.data.join(", ")}\n` : "",
    resumeFrom: a.fromModel, skipToWriting: a.skipToWriting });
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
  const { startServer } = await import("@solvex/web");
  await startServer({ port: a.port, sessionRoot: a.sessionDir ?? SESSION_ROOT });
  process.stdout.write(`SolveX WebUI 2.0: http://127.0.0.1:${a.port}/\n`);
  return 0; // 常驻进程
}

async function main(): Promise<void> {
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
