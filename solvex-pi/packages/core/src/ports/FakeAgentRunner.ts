import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, relative, sep } from "node:path";
import type { AgentRunner, RunRequest, RunResult } from "./AgentRunner.js";
import { DIR } from "../workspace/paths.js";

export type FakeOutcome = { text?: string; files?: Record<string, string>; fail?: string };
export type FakeHandler = (req: RunRequest) => FakeOutcome | undefined;

export type FakeOptions = {
  models?: string[];
  handlers?: FakeHandler[];
  failTaskIds?: string[];
  delayMs?: number;
  onCall?: (req: RunRequest) => void;
  /** 演示模式：合成 Pi 原生 thinking/turn/tool/usage 事件，供 WebUI 三视图展示。 */
  synthetic?: boolean;
};

const SUMMARY = [
  "# Model Results Summary", "", "## Key Numerical Results", "Objective value: 42.0", "",
  "## Sanity Checks", "All sums and ranges verified.", "", "## Model Parameters", "alpha = 0.5", "",
  "## Data Files Generated", "results.csv (10 rows, 3 columns)", "", "## Figures",
  "fig1.png: convergence curve", "", "## Issues or Limitations", "None.", "",
  "VERIFICATION_RESULT: SATISFIED", "",
].join("\n");

/** 0 次模型调用即可跑通完整四阶段的 FakeRunner（T2.1 / CP2）。
 *  默认按 role + taskId 自动落盘兼容产物；可用 handlers 覆盖任意一次调用。 */
export class FakeAgentRunner implements AgentRunner {
  readonly calls: RunRequest[] = [];
  constructor(private readonly opts: FakeOptions = {}) {}

  async run(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    if (signal?.aborted) throw new Error("aborted");
    this.calls.push(req);
    this.opts.onCall?.(req);
    if (this.opts.delayMs) await new Promise((r) => setTimeout(r, this.opts.delayMs));
    if (signal?.aborted) throw new Error("aborted");

    if (this.opts.failTaskIds?.includes(req.taskId ?? "")) throw new Error(`fake failure: ${req.taskId}`);
    if (this.opts.synthetic) this.emitSynthetic(req);

    const override = this.opts.handlers?.map((h) => h(req)).find((x) => x !== undefined);
    const outcome: FakeOutcome = override ?? this.auto(req);
    if (outcome.fail) throw new Error(outcome.fail);

    const files: Record<string, string> = outcome.files ?? {};
    for (const [rel, content] of Object.entries(files)) {
      const abs = join(req.cwd, rel);
      mkdirSync(abs.slice(0, abs.lastIndexOf(sep)), { recursive: true });
      writeFileSync(abs, content);
    }
    return {
      text: outcome.text ?? SUMMARY,
      artifacts: Object.keys(files).map((p) => relative(req.cwd, join(req.cwd, p))),
      usage: { input: 100, output: 50, cost: 0.01 },
      settled: true,
    };
  }

  /** 合成 §4.6 内层事件：让无凭据演示也能展示思考过程 / 运行阶段 / 用量条。 */
  private emitSynthetic(req: RunRequest): void {
    const taskId = req.taskId ?? "unknown";
    const e = (ev: Record<string, unknown>) => req.onEvent?.({ ...ev, ts: Date.now() } as any);
    const block = `${taskId}:0`;
    const thinking = "分析问题结构，识别核心数学挑战，设计多模型方案。";
    e({ type: "lifecycle", taskId, state: "agent_start" });
    e({ type: "model", taskId, provider: "demo", model: "fake-runner", thinkingLevel: req.thinkingLevel });
    e({ type: "turn", taskId, state: "start", turn: 1 });
    e({ type: "thinking", taskId, state: "start", blockId: block, contentIndex: 0 });
    for (const delta of ["分析问题结构，", "识别核心数学挑战，", "设计多模型方案。"])
      e({ type: "thinking", taskId, state: "delta", blockId: block, contentIndex: 0, delta });
    e({ type: "thinking", taskId, state: "end", blockId: block, contentIndex: 0, content: thinking });
    e({ type: "output", taskId, state: "delta", blockId: `${taskId}:1`, contentIndex: 1, delta: "正在写入产物…" });
    e({ type: "output", taskId, state: "end", blockId: `${taskId}:1`, contentIndex: 1, content: "正在写入产物…" });
    e({ type: "tool", taskId, toolCallId: `${taskId}-w1`, name: "write", state: "start", args: { path: "output" } });
    e({ type: "tool", taskId, toolCallId: `${taskId}-w1`, name: "write", state: "end", result: "ok", isError: false });
    e({ type: "usage", taskId, input: 120, output: 80, cacheRead: 0, cacheWrite: 0,
         totalTokens: 200, cost: 0.002, cumulative: false });
    e({ type: "turn", taskId, state: "end", turn: 1 });
    e({ type: "lifecycle", taskId, state: "agent_end" });
    e({ type: "lifecycle", taskId, state: "agent_settled" });
  }

  private modelOf(req: RunRequest): string | undefined {
    return req.taskId?.match(/:(model_[a-z0-9_]+)/)?.[1];
  }

  /** 自动产出与旧 workspace 契约兼容的文件（§2.5）。 */
  private auto(req: RunRequest): FakeOutcome {
    const isReview = req.taskId?.startsWith("P2-REVIEW") || /reviewing the implementation results/i.test(req.task);
    const isPlan = req.taskId === "P1" || (!isReview && req.role === "modeling" && /Master Plan/i.test(req.task));

    if (isPlan) {
      const models = this.opts.models ?? ["Model 1", "Model 2", "Model 3"];
      const plan = ["# Master Plan", "", "## Overview", "Multi-model strategy", "",
        ...models.flatMap((m, i) => [
          `## ${m}: Approach ${i + 1}`, "### Purpose", "Solve a sub-problem", "",
          "### Mathematical Formulation", "min f(x) s.t. Ax <= b", "",
          "### Solution Strategy", "Use scipy.optimize.linprog", "",
          "### Expected Outputs", "results.csv and fig1.png", "",
          "### Validation", "Check constraints", "",
        ]),
        "## Integration", "Combine the model outputs.", ""].join("\n");
      return { text: "Master Plan written. VERIFICATION_RESULT: SATISFIED",
               files: { [`${DIR.modeling}/master_plan.md`]: plan } };
    }
    if (isReview) {
      const m = this.modelOf(req) ?? "model_1";
      return { text: "VERIFICATION_RESULT: SATISFIED",
               files: { [`${DIR.modeling}/${m}_review.md`]:
                 "# Review\n\nNumerically sound.\n\nVERIFICATION_RESULT: SATISFIED\n" } };
    }
    if (req.role === "writing") {
      return { text: "Paper written.",
               files: { [`${DIR.paper}/main.tex`]: "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n" } };
    }
    // programming / fix / revision
    const m = this.modelOf(req) ?? "model_1";
    const base = `${DIR.programming}/${m}`;
    return {
      text: "VERIFICATION_RESULT: SATISFIED",
      files: {
        [`${base}/model.py`]: "import numpy as np\nprint(42.0)\n",
        [`${base}/results_summary.md`]: SUMMARY,
        [`${base}/results.csv`]: "id,probability\n1,0.2\n2,0.3\n",
        [`${base}/figures/fig1.png`]: "fake-png",
        [`${base}/handoff.json`]: JSON.stringify({ status: "satisfied", issues: [],
          fixInstructions: "", summaryPath: `${base}/results_summary.md` }),
      },
    };
  }
}
