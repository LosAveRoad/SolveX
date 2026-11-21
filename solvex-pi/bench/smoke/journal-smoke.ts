/** 真实 Pi SDK + GLM 的断点续跑冒烟：子进程跑到一半被 SIGKILL → 续跑 → 回放 → 同一会话追加调用。
 *  用法: MISTRAL_GW_KEY=local SOLVEX_MODELS_PATH=bench/models.gateway.json \
 *        npx tsx --tsconfig bench/tsconfig.json bench/smoke/journal-smoke.ts [phase] [cwd] */
import { mkdtempSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { EventBus } from "@solvex/core";
import { PiAgentRunner, sharedModelRuntime, inspectJournal } from "@solvex/pi-runtime";

const [phase = "driver", dirArg] = process.argv.slice(2);
const TASK = "Do these steps strictly one tool call at a time, in order: " +
  "(1) bash `sleep 2; echo alpha > a.txt` (2) bash `sleep 2; echo beta > b.txt` (3) bash `sleep 2; echo gamma > c.txt` " +
  "(4) bash `sleep 2; cat a.txt b.txt c.txt > done.txt`. Then reply with exactly: FINISHED";
const journal = (cwd: string) => join(cwd, ".solvex/journal", "P2-IMPL_model_1.jsonl");

async function runOnce(cwd: string, call: string, task: string) {
  const modelRuntime = await sharedModelRuntime();
  const runner = new PiAgentRunner({ bus: new EventBus(), modelRuntime: modelRuntime!, mcpConfigPath: join(cwd, "no-mcp.json") });
  const t0 = Date.now();
  const r = await runner.run({ role: "programming", systemPrompt: "You are a careful agent.\n\n{{AVAILABLE_TOOLS}}",
    task, cwd, taskId: "P2-IMPL:model_1", phase: 2, maxTurns: 20, thinkingLevel: "low" as any,
    model: { provider: "mistralgw", id: "zai-glm-5-3-flash" },
    journal: { path: journal(cwd), call } });
  return { ...r, ms: Date.now() - t0 };
}

if (phase === "child") {
  await runOnce(dirArg!, "impl", TASK);
  process.exit(0);
}

const cwd = mkdtempSync(join(tmpdir(), "solvex-journal-smoke-"));
console.log("cwd", cwd);
// A：子进程跑，日志里出现第 2 次工具结果后 SIGKILL（模拟进程被杀，不给任何收尾机会）
const child = spawn("npx", ["tsx", "--tsconfig", "bench/tsconfig.json", "bench/smoke/journal-smoke.ts", "child", cwd],
  { stdio: "ignore", env: process.env });
await new Promise<void>((resolve) => {
  const t = setInterval(() => {
    const p = journal(cwd);
    if (!existsSync(p)) return;
    const results = readFileSync(p, "utf-8").split("\n").filter((l) => l.includes('"role":"toolResult"')).length;
    if (results >= 2) { child.kill("SIGKILL"); clearInterval(t); resolve(); }
  }, 200);
  child.on("exit", () => { clearInterval(t); resolve(); });
});
await new Promise((r) => setTimeout(r, 300));
const before = inspectJournal(journal(cwd), "impl");
console.log("A killed:", { turns: before.turns, prompted: before.prompted, done: !!before.done,
  files: ["a.txt", "b.txt", "c.txt", "done.txt"].filter((f) => existsSync(join(cwd, f))) });

// B：续跑
const b = await runOnce(cwd, "impl", TASK);
console.log("B resume:", { resumed: b.resumed, replayed: b.replayed, text: b.text.trim().slice(0, 60), ms: b.ms,
  usage: b.usage, doneTxt: existsSync(join(cwd, "done.txt")) ? readFileSync(join(cwd, "done.txt"), "utf-8").trim().split("\n") : null });
const after = inspectJournal(journal(cwd), "impl");
console.log("   journal:", { turns: after.turns, done: after.done });

// C：回放
const c = await runOnce(cwd, "impl", TASK);
console.log("C replay:", { replayed: c.replayed, text: c.text.trim().slice(0, 60), ms: c.ms });

// D：同一会话追加一次调用（评审修复意见就是这样注入的），验证继承上下文（不许用工具，只凭对话记忆回答）
const d = await runOnce(cwd, "fix-1", "Without using any tool, answer from memory: which files did you create in this " +
  "session, in order, and what did done.txt contain? One line.");
console.log("D same-session call:", { resumed: d.resumed, text: d.text.trim().slice(0, 200), usage: d.usage, ms: d.ms });

// E：两次调用都回放
const e1 = await runOnce(cwd, "impl", TASK), e2 = await runOnce(cwd, "fix-1", "x");
console.log("E replay both:", { impl: e1.replayed, fix: e2.replayed, fixText: e2.text.trim().slice(0, 60) });
