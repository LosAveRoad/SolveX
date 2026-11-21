/**
 * 提交工具真实模型冒烟（ADR-0015）：经网关调 GLM 5.3 Flash，三个小场景各跑 N 次，
 * 看模型是否调用提交工具、被拒绝后能否补齐再提交。
 *
 *   MISTRAL_GW_KEY=local SOLVEX_MODELS_PATH=bench/models.gateway.json npx tsx --tsconfig bench/tsconfig.json bench/probe/submit_smoke.ts [N]
 *
 * 结果写到 bench/results/submit-smoke/results.json。
 */
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  EventBus, ROLE_TOOLS, reviewSystem, programmingSystem, writingSystem, reviewSubmitTool, fixSubmitTool,
  paperSubmitTool, fingerprint, submitInstruction, submitNudge, REVIEW_OUTPUT_POLICY, type RunRequest, type SubmitTool,
} from "@solvex/core";
import { PiAgentRunner, sharedModelRuntime } from "@solvex/pi-runtime";

const N = Number(process.argv[2] ?? 2);
const MODEL = { provider: "mistralgw", id: "zai-glm-5-3-flash" };

type Outcome = { scenario: string; rep: number; submitted: boolean; nudges: number; rejections: number;
                 toolCalls: number; seconds: number; note?: string };

async function main() {
  const bus = new EventBus();
  let rejections = 0, toolCalls = 0;
  bus.subscribe((e: any) => {
    if (e.type === "tool" && e.state === "end" && /^submit_/.test(e.name ?? "")) {
      toolCalls++;
      if (e.isError) rejections++;
    }
  });
  const modelRuntime = await sharedModelRuntime();
  if (!modelRuntime?.resolve(MODEL.provider, MODEL.id)) throw new Error("set SOLVEX_MODELS_PATH=bench/models.gateway.json");
  const runner = new PiAgentRunner({ bus, modelRuntime });
  const out: Outcome[] = [];

  const run = async (scenario: string, rep: number, cwd: string, role: RunRequest["role"], sys: string,
                     task: string, submit: SubmitTool, after?: () => string) => {
    rejections = 0; toolCalls = 0;
    const t0 = Date.now();
    const base: RunRequest = { role, systemPrompt: sys, task, cwd, tools: ROLE_TOOLS[role], maxTurns: 30,
      model: MODEL, thinkingLevel: "xhigh", taskId: `${scenario}-${rep}`, phase: 2, submit,
      journal: { path: join(cwd, ".solvex/journal/s.jsonl"), call: "main" } };
    let r = await runner.run(base);
    let nudges = 0;
    while (!r.submitted && nudges < 2) {
      nudges++;
      r = await runner.run({ ...base, task: submitNudge(submit.name), journal: { ...base.journal!, call: `submit-${nudges}` } });
    }
    const o: Outcome = { scenario, rep, submitted: !!r.submitted, nudges, rejections, toolCalls,
      seconds: Math.round((Date.now() - t0) / 1000), ...(after ? { note: after() } : {}) };
    console.log(JSON.stringify(o));
    out.push(o);
  };

  for (let rep = 1; rep <= N; rep++) {
    // 1) 评审：结果里有一个算错的数（0.62 + 0.45 > 1）。
    {
      const cwd = mkdtempSync(join(tmpdir(), "smoke-review-"));
      const d = join(cwd, "02_programming/model_1");
      mkdirSync(d, { recursive: true });
      writeFileSync(join(d, "results.json"), JSON.stringify({ p_win_A: 0.62, p_win_B: 0.45 }));
      writeFileSync(join(d, "run.py"), "import json\njson.dump({'p_win_A':0.62,'p_win_B':0.45},open('results.json','w'))\n");
      const summary = "# Results\nTwo contestants A and B; exactly one wins.\nP(A wins) = 0.62, P(B wins) = 0.45.\n";
      writeFileSync(join(d, "results_summary.md"), summary);
      const task = `Review Model 1 in ${d}/. Problem: estimate the win probabilities of two contestants (exactly one wins).\n` +
        `PROGRAMMER'S RESULTS REPORT:\n${summary}` + REVIEW_OUTPUT_POLICY;
      let verdict = "";
      const sub = reviewSubmitTool();
      const wrapped: SubmitTool = { ...sub, check: async (a) => { const r = await sub.check(a); if (r === null) verdict = String(a.verdict); return r; } };
      await run("review", rep, cwd, "review", reviewSystem(), task, wrapped, () => `verdict=${verdict}`);
    }
    // 2) 修复：run.py 里的归一化写错，要求改代码并更新摘要。
    {
      const cwd = mkdtempSync(join(tmpdir(), "smoke-fix-"));
      const d = join(cwd, "02_programming/model_1");
      mkdirSync(d, { recursive: true });
      writeFileSync(join(d, "run.py"), "import json\nw=[3,2]\np=[x/4 for x in w]\njson.dump({'p_win_A':p[0],'p_win_B':p[1]},open('results.json','w'))\n");
      writeFileSync(join(d, "results.json"), JSON.stringify({ p_win_A: 0.75, p_win_B: 0.5 }));
      writeFileSync(join(d, "results_summary.md"), "# Results\nP(A wins) = 0.75, P(B wins) = 0.5.\n");
      const task = `=== CROSS-REVIEW ROUND 1/3: Fix Model 1 ===\n=== FIX INSTRUCTIONS ===\nThe probabilities sum to 1.25. ` +
        `run.py divides by 4 instead of sum(w). Normalise by sum(w), re-run run.py, and update results_summary.md.\n` +
        `Model directory: ${d}/` + submitInstruction("submit_fix", "the fix is applied and the outputs are regenerated");
      await run("fix", rep, cwd, "programming", programmingSystem(), task,
        fixSubmitTool({ modelDir: d, baseline: fingerprint(d), requireSummary: true }),
        () => `results=${readFileSync(join(d, "results.json"), "utf-8")}`);
    }
    // 3) 论文：缺 Model 2 一节和结论，题面要求备忘录。
    {
      const cwd = mkdtempSync(join(tmpdir(), "smoke-paper-"));
      const p = join(cwd, "04_paper/main.tex");
      mkdirSync(join(cwd, "04_paper"), { recursive: true });
      writeFileSync(p, "\\documentclass{article}\n\\begin{document}\n\\begin{abstract}\n" +
        "We model weekly fan votes in a dance competition with a Bayesian rank model (Model 1) and a share regression " +
        "(Model 2). Model 1 reproduces 15 of 34 eliminations; Model 2 explains 47.7% of variance in judge-fan gaps. " +
        "We compare rank-based and percentage-based aggregation and recommend the rank rule for fairness and stability.\n" +
        "\\end{abstract}\n\\section{Model 1: Bayesian Rank Model}\nReproduces 15/34 eliminations.\n\\end{document}\n");
      const problem = "Estimate fan votes with two models and write a paper. Include a one-page memo to the producers.";
      const task = `PROBLEM:\n${problem}\n\nThe paper at ${p} is unfinished. Results: Model 1 reproduces 15/34 eliminations; ` +
        `Model 2 (share regression) R^2 = 0.477. Finish the paper (keep it short — a few paragraphs per section).` +
        submitInstruction("submit_paper", "the whole paper is written (pass the memo the problem asks for as its `memo` argument — do not write it into main.tex)");
      await run("paper", rep, cwd, "writing", writingSystem(), task,
        paperSubmitTool({ paperPath: p, modelCount: 2, problem }),
        () => `memo.tex=${existsSync(join(cwd, "04_paper/memo.tex"))} input=${readFileSync(p, "utf-8").includes("\\input{memo}")}`);
    }
  }
  mkdirSync("bench/results/submit-smoke", { recursive: true });
  writeFileSync("bench/results/submit-smoke/results.json", JSON.stringify(out, null, 2));
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
