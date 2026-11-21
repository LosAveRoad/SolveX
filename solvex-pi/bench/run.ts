/**
 * SolveX 真实模型基准运行器（经 mistral-gateway 调 GLM 5.3 Flash）。
 *
 * 用法:
 *   MISTRAL_GW_KEY=local SOLVEX_MODELS_PATH=bench/models.gateway.json \
 *     npx tsx bench/run.ts --label r0-c3 --concurrency 3
 *     npx tsx bench/run.ts --label r6-c3 --resume <bench/sessions 下的会话 id>   # 退出后接着跑
 *
 * 产出 bench/results/<label>/{events.jsonl, metrics.json}，会话产物在 bench/sessions/<label>-*。
 * 不修改任何生产配置（~/.solvex 不读不写），模型/并发/思考档全部在这里显式给出。
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import {
  EventBus, SolveXFlow, prepareWorkspace, ingestData, DEFAULT_CONFIG,
  type ModelConfig, type SolveXEvent, type ThinkingLevel,
} from "@solvex/core";
import { PiAgentRunner, sharedModelRuntime } from "@solvex/pi-runtime";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const GATEWAY = process.env.MISTRAL_GW_URL ?? "http://127.0.0.1:8788";

type Args = { label: string; concurrency: number; problem: string; data: string[];
  provider: string; model: string; thinking: ThinkingLevel; extensions: string[];
  /** 续跑已有的基准会话（bench/sessions/<id>）：已完成的调用从会话日志回放。 */
  resume?: string;
  /** 上下文超过这个 token 数就压缩；0 = 沿用 Pi 默认（窗口 − 16K）。不传用产品默认。 */
  compactAt?: number };

function parse(argv: string[]): Args {
  const a: Args = { label: `run-${Date.now().toString(36)}`, concurrency: 3,
    problem: join(ROOT, "paper/problem/problem-focused.md"),
    data: [join(ROOT, "paper/problem/2026_MCM_Problem_C_Data.csv")],
    provider: "mistralgw", model: "zai-glm-5-3-flash", thinking: "xhigh"   /* ADR-0014：质量优先，网关映射为 max */, extensions: [] };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === "--label") { a.label = v; i++; }
    else if (k === "--concurrency") { a.concurrency = Number(v); i++; }
    else if (k === "--problem") { a.problem = resolve(v); i++; }
    else if (k === "--data") { a.data = [resolve(v)]; i++; }
    else if (k === "--model") { a.model = v; i++; }
    else if (k === "--thinking") { a.thinking = v as ThinkingLevel; i++; }
    else if (k === "--resume") { a.resume = v; i++; }
    else if (k === "--compact-at") { a.compactAt = Number(v); i++; }
    else throw new Error(`unknown arg ${k}`);
  }
  return a;
}

async function gatewayUsage(): Promise<Record<string, number> | null> {
  try {
    const r = await fetch(`${GATEWAY}/usage`);
    const j: any = await r.json();
    const out = { requests: 0, prompt_tokens: 0, cached_tokens: 0, completion_tokens: 0 };
    for (const row of j.usage ?? []) for (const k of Object.keys(out))
      (out as any)[k] += Number(row[k] ?? 0);
    return out;
  } catch { return null; }
}

/** 写入路径分类：并行任务是否越出自己的 02_programming/<model>/ 目录。 */
function classifyWrite(wsDir: string, taskId: string, rawPath: string): string {
  const abs = resolve(wsDir, rawPath);
  const rel = relative(wsDir, abs).split(sep).join("/");
  if (rel.startsWith("..")) return "outside_workspace";
  const m = /^P2-(IMPL|REVIEW):(.+)$/.exec(taskId);
  if (!m) return "ok";
  const own = `02_programming/${m[2]}/`;
  if (rel.startsWith(own)) return "ok";
  if (rel === "01_modeling/master_plan.md" || rel.endsWith("all_results_summary.md")) return "shared_file";
  if (rel.startsWith("02_programming/")) return "other_model_dir";
  return "outside_own_dir";
}

async function main() {
  const args = parse(process.argv.slice(2));
  const outDir = join(ROOT, "bench/results", args.label);
  mkdirSync(outDir, { recursive: true });
  const eventsFile = join(outDir, "events.jsonl");
  // 续跑时追加事件（上一段运行的事件保留），否则清空。
  if (!args.resume) writeFileSync(eventsFile, "");

  const sessionsRoot = join(ROOT, "bench/sessions");
  let problem: string, ws;
  if (args.resume) {
    ws = prepareWorkspace({ root: sessionsRoot, sessionId: args.resume, mode: "resume" });
    problem = readFileSync(join(ws.paths.problem, "problem.md"), "utf-8");     // 沿用首次运行的题面
  } else {
    problem = readFileSync(args.problem, "utf-8");
    ws = prepareWorkspace({ root: sessionsRoot, problem, sessionId: `${args.label}-${Date.now().toString(36)}` });
    await ingestData(ws, args.data);
  }

  const phase = (thinkingLevel: ThinkingLevel) =>
    ({ provider: args.provider, model: args.model, thinkingLevel });
  const config: ModelConfig = {
    ...DEFAULT_CONFIG,
    defaults: { provider: args.provider, model: args.model, thinkingLevel: args.thinking },
    byPhase: { P1: phase(args.thinking), P2_IMPL: phase(args.thinking),
      P2_REVIEW: phase(args.thinking), P3: phase("off"), P4: phase(args.thinking) },
    concurrency: args.concurrency, strict: false,
  };

  // ---- 指标采集 ----
  const t0 = Date.now();
  const stages: Record<string, { start?: number; end?: number; state?: string }> = {};
  const tools: Record<string, { calls: number; errors: number; byName: Record<string, number> }> = {};
  const writes: { taskId: string; tool: string; path: string; cls: string; blocked?: boolean }[] = [];
  const warns: { taskId?: string; message: string }[] = [];
  const finalMsgUsage: Record<string, { input: number; output: number; cacheRead: number; msgs: number }> = {};
  const lifecycle: Record<string, number> = {};
  const toolArgs = new Map<string, { taskId: string; name: string; path?: string }>();
  let deltaEvents = 0;

  const bus = new EventBus();
  bus.subscribe((e: SolveXEvent) => {
    const ev: any = e;
    // 体积控制：流式 delta 只计数不落盘
    if ((ev.type === "thinking" || ev.type === "output") && ev.state === "delta") { deltaEvents++; return; }
    if (ev.type === "tool" && (ev.state === "delta" || ev.state === "update")) { deltaEvents++; return; }
    const slim = ev.type === "output" && ev.state === "final"
      ? { ...ev, message: { role: ev.message?.role, usage: ev.message?.usage, stopReason: ev.message?.stopReason } }
      : ev.type === "tool" && ev.state === "end" ? { ...ev, result: undefined } : ev;
    appendFileSync(eventsFile, JSON.stringify(slim) + "\n");

    const tid = ev.taskId ?? "unknown";
    if (ev.type === "stage") {
      const s = (stages[ev.node.id] ??= {});
      if (ev.node.state === "running") s.start ??= ev.node.startedAt ?? ev.ts;
      if (["done", "failed", "aborted", "skipped"].includes(ev.node.state)) s.end = ev.node.endedAt ?? ev.ts;
      s.state = ev.node.state;
    } else if (ev.type === "tool" && ev.state === "start" && ev.args !== undefined) {
      const t = (tools[tid] ??= { calls: 0, errors: 0, byName: {} });
      t.calls++; t.byName[ev.name] = (t.byName[ev.name] ?? 0) + 1;
      const p = ev.args?.path ?? ev.args?.file_path;
      toolArgs.set(ev.toolCallId, { taskId: tid, name: ev.name, path: p });
      if ((ev.name === "write" || ev.name === "edit") && typeof p === "string")
        writes.push({ taskId: tid, tool: ev.name, path: p, cls: classifyWrite(ws.dir, tid, p) });
    } else if (ev.type === "tool" && ev.state === "end" && ev.isError) {
      (tools[tid] ??= { calls: 0, errors: 0, byName: {} }).errors++;
      const a = toolArgs.get(ev.toolCallId);
      const w = a && writes.findLast((x) => x.taskId === a.taskId && x.path === a.path);
      if (w) w.blocked = true;
    } else if (ev.type === "output" && ev.state === "final" && ev.message?.role === "assistant") {
      const u = ev.message?.usage ?? {};
      const f = (finalMsgUsage[tid] ??= { input: 0, output: 0, cacheRead: 0, msgs: 0 });
      f.input += u.input ?? 0; f.output += u.output ?? 0; f.cacheRead += u.cacheRead ?? 0; f.msgs++;
    } else if (ev.type === "warn") {
      warns.push({ taskId: ev.taskId, message: ev.message });
    } else if (ev.type === "lifecycle") {
      const k = `${ev.state}${ev.detail ? ":" + ev.detail : ""}`;
      lifecycle[k] = (lifecycle[k] ?? 0) + 1;
    } else if (ev.type === "status" || ev.type === "done" || ev.type === "barrier") {
      process.stdout.write(`[${((Date.now() - t0) / 1000).toFixed(0)}s] ${ev.type} ${ev.message ?? `${ev.id} ${ev.state} ${ev.completed}/${ev.total}`}\n`);
    }
  });

  const modelRuntime = await sharedModelRuntime();
  if (!modelRuntime) throw new Error("ModelRuntime init failed");
  if (!modelRuntime.resolve(args.provider, args.model))
    throw new Error(`model ${args.provider}/${args.model} not found — set SOLVEX_MODELS_PATH=bench/models.gateway.json`);
  const runner = new PiAgentRunner({ bus, modelRuntime,
    ...(args.compactAt !== undefined ? { compactAtTokens: args.compactAt || Number.POSITIVE_INFINITY } : {}),
    mcpConfigPath: join(outDir, "no-mcp.json") /* 不存在 → 不启用 MCP，隔离变量 */ });

  const gwBefore = await gatewayUsage();
  const dataInfo = `\nDATA FILES: ${args.data.map((d) => `data/${d.split("/").pop()}`).join(", ")}\n`;
  // 上游瞬时中断（r0、r6 实测：SSL EOF 持续超过 SDK 约 2 分钟的重试窗口）时用产品自己的断点续跑：
  // 等待后在同一工作区重新执行流水线，已完成的调用从会话日志回放，中断的接着跑（ADR-0013）。
  // r6 实测上游中断可持续 10 分钟以上：等待按 1、2、4、8、10、10 分钟递增。
  const MAX_RESUMES = 6;
  const backoffMs = (n: number) => Math.min(60_000 * 2 ** n, 600_000);
  let summary: any, error: string | undefined;
  const resumes: { atMs: number; reason: string }[] = [];
  for (let attempt = 0; ; attempt++) {
    summary = undefined; error = undefined;
    try { summary = await new SolveXFlow({ runner, bus, ws, config, problem, dataInfo }).run(); }
    catch (e: any) { error = String(e?.stack ?? e); }
    const retryable = (error && /AgentRunError/.test(error)) || summary?.status === "failed";
    if (!retryable || attempt >= MAX_RESUMES) break;
    const reason = (error ?? `status=${summary?.status}`).split("\n")[0].slice(0, 300);
    resumes.push({ atMs: Date.now() - t0, reason });
    const wait = backoffMs(attempt);
    process.stdout.write(`[${((Date.now() - t0) / 1000).toFixed(0)}s] resume ${attempt + 1}/${MAX_RESUMES} in ${wait / 1000}s: ${reason}\n`);
    await new Promise((r) => setTimeout(r, wait));
  }
  const gwAfter = await gatewayUsage();

  // ---- 汇总 ----
  const dur = (id: string) => stages[id]?.start && stages[id]?.end ? stages[id].end! - stages[id].start! : 0;
  const ids = Object.keys(stages);
  const impl = ids.filter((i) => i.startsWith("P2-IMPL:"));
  const review = ids.filter((i) => i.startsWith("P2-REVIEW:"));
  const span = (xs: string[]) => {
    const s = xs.map((x) => stages[x]?.start).filter(Boolean) as number[];
    const e = xs.map((x) => stages[x]?.end).filter(Boolean) as number[];
    return s.length && e.length ? Math.max(...e) - Math.min(...s) : 0;
  };
  const sum = (xs: string[]) => xs.reduce((a, x) => a + dur(x), 0);
  const fm = Object.values(finalMsgUsage).reduce((a, u) =>
    ({ input: a.input + u.input, output: a.output + u.output, cacheRead: a.cacheRead + u.cacheRead, msgs: a.msgs + u.msgs }),
    { input: 0, output: 0, cacheRead: 0, msgs: 0 });
  const gwDelta = gwBefore && gwAfter ? Object.fromEntries(Object.keys(gwAfter).map((k) => [k, gwAfter[k] - gwBefore[k]])) : null;
  const writeCls = writes.reduce((a, w) => { a[w.cls] = (a[w.cls] ?? 0) + 1; return a; }, {} as Record<string, number>);
  const paper = join(ws.paths.paper, "main.tex");

  const metrics = {
    label: args.label, model: `${args.provider}/${args.model}`, thinking: args.thinking,
    concurrency: args.concurrency, compactAt: args.compactAt ?? "default", sessionDir: ws.dir, status: summary?.status ?? "crashed", error, resumes,
    wallMs: Date.now() - t0,
    stagesMs: Object.fromEntries(ids.map((i) => [i, dur(i)])),
    stageStates: Object.fromEntries(ids.map((i) => [i, stages[i].state])),
    parallel: {
      implWallMs: span(impl), implSumMs: sum(impl),
      reviewWallMs: span(review), reviewSumMs: sum(review),
      implSpeedup: span(impl) ? +(sum(impl) / span(impl)).toFixed(2) : null,
      reviewSpeedup: span(review) ? +(sum(review) / span(review)).toFixed(2) : null,
    },
    tokens: {
      solvexReported: { total: summary?.totalTokens ?? null, byTask: summary?.usageByTask ?? null },
      finalMessages: fm,
      gateway: gwDelta,
    },
    tools, writes, writeClasses: writeCls, warns, lifecycle, deltaEvents,
    models: summary?.models ?? null, issues: summary?.issues ?? null,
    paper: { exists: existsSync(paper), bytes: existsSync(paper) ? readFileSync(paper).length : 0 },
  };
  // 续跑段的指标单独落盘（只覆盖这一段），首段的 metrics.json 保留。
  const metricsFile = join(outDir, args.resume ? `metrics.resume-${Date.now().toString(36)}.json` : "metrics.json");
  writeFileSync(metricsFile, JSON.stringify(metrics, null, 2));
  process.stdout.write(`\n== ${args.label}: ${metrics.status} in ${(metrics.wallMs / 1000).toFixed(0)}s; ` +
    `metrics → ${relative(ROOT, metricsFile)}\n`);
  process.exit(0); // MCP/SDK 句柄可能残留，显式退出
}

main().catch((e) => { console.error(e); process.exit(1); });
