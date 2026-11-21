import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import {
  prepareWorkspace, FakeAgentRunner, FAKE_REVIEW_BODY, FAKE_REVIEW_OK, fakeSubmit, EventBus, SolveXFlow, DEFAULT_CONFIG,
  ROLE_TOOLS, renderReview, scopeProblem, DOWNSTREAM_PROBLEM_NOTE, type SolveXEvent, type ModelConfig,
  type FakeOutcome,
} from "@solvex/core";

const MODELS = ["Model 1", "Model 2", "Model 3"];

/** 模拟 PiAgentRunner 的日志语义：有完成记录就回放，否则调用内层 runner 并记录结果。 */
function journaling(inner: FakeAgentRunner, crash?: (req: any) => boolean) {
  return {
    calls: inner.calls,
    async run(req: any, signal?: AbortSignal) {
      const p: string | undefined = req.journal?.path;
      const call = req.journal?.call ?? "main";
      const done = p && existsSync(p) ? JSON.parse(readFileSync(p, "utf-8")) : {};
      const rec = done[call];
      if (rec) return { text: rec.text, artifacts: [], settled: true, replayed: true,
                        usage: { input: 0, output: 0, cost: 0 }, ...(rec.submitted ? { submitted: rec.submitted } : {}) };
      if (crash?.(req)) throw new Error("process killed");
      const r = await inner.run(req, signal);
      if (p) { mkdirSync(dirname(p), { recursive: true });
               writeFileSync(p, JSON.stringify({ ...done, [call]: { text: r.text, submitted: r.submitted } })); }
      return r;
    },
  } as any;
}
function setup(opts: { concurrency?: number; strict?: boolean; runner?: FakeAgentRunner } = {}) {
  const root = mkdtempSync(join(tmpdir(), "solvex-flow-"));
  const ws = prepareWorkspace({ root, sessionId: "flow", problem: "Test problem" });
  const bus = new EventBus();
  const events: SolveXEvent[] = [];
  bus.subscribe((e) => events.push(e));
  const runner = opts.runner ?? new FakeAgentRunner({ models: MODELS });
  const config: ModelConfig = { ...DEFAULT_CONFIG, concurrency: opts.concurrency ?? 3, strict: opts.strict ?? false };
  const flow = new SolveXFlow({ runner, bus, ws, config, problem: "Test problem", dataInfo: "" });
  return { ws, bus, events, runner, flow, config };
}

describe("T2.8 四阶段状态机（FakeRunner 全流程，0 次模型调用）", () => {
  it("CP2：concurrency=3 跑通完整四阶段并产出兼容目录", async () => {
    const { ws, runner, flow } = setup({ concurrency: 3 });
    const summary = await flow.run();
    expect(summary.status).toBe("completed");
    expect(summary.models).toHaveLength(3);
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
    expect(existsSync(join(ws.paths.programming, "all_results_summary.md"))).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
    for (const d of ["model_1", "model_2", "model_3"]) {
      expect(existsSync(join(ws.paths.programming, d, "results_summary.md"))).toBe(true);
      expect(existsSync(join(ws.paths.programming, d, "figures/fig1.png"))).toBe(true);
      expect(existsSync(join(ws.paths.modeling, `${d}_review.md`))).toBe(true);
    }
    expect(runner.calls.length).toBeGreaterThanOrEqual(8); // P1 + 3 IMPL + 3 REVIEW + P4
    const all = readFileSync(join(ws.paths.programming, "all_results_summary.md"), "utf-8");
    expect(all).toContain("## Model 1");
    expect(all).toContain("Total models implemented: 3");
  });

  it("concurrency=1 与 =3 的共享产物逐字节一致（R11 写安全）", async () => {
    const a = setup({ concurrency: 1 }); await a.flow.run();
    const b = setup({ concurrency: 3 }); await b.flow.run();
    for (const f of ["01_modeling/master_plan.md", "02_programming/all_results_summary.md",
                     "04_paper/main.tex"])
      expect(readFileSync(join(b.ws.dir, f))).toEqual(readFileSync(join(a.ws.dir, f)));
  });

  it("A2/F3：评审只给只读工具且 master_plan 字节不变", async () => {
    const { ws, runner, flow } = setup();
    await flow.run();
    const planBefore = readFileSync(join(ws.paths.modeling, "master_plan.md"));
    const reviews = runner.calls.filter((c) => c.taskId?.startsWith("P2-REVIEW"));
    expect(reviews).toHaveLength(3);
    for (const r of reviews) expect(r.tools).toEqual(ROLE_TOOLS.review);
    expect(readFileSync(join(ws.paths.modeling, "master_plan.md"))).toEqual(planBefore);
  });

  it("R11：并行任务 writablePrefixes 只含自己目录，不含共享文件", async () => {
    const { runner, flow } = setup({ concurrency: 3 });
    await flow.run();
    for (const c of runner.calls.filter((x) => x.taskId?.startsWith("P2-IMPL"))) {
      expect(c.writablePrefixes).toEqual([`02_programming/${c.taskId!.split(":")[1]}/`]);
      expect(c.writablePrefixes!.some((p) => p.includes("master_plan") || p.includes("all_results"))).toBe(false);
    }
    // all_results_summary.md 由纯代码生成，没有任何 LLM 会话写它
    expect(runner.calls.every((c) => !c.task?.includes("write all_results_summary.md"))).toBe(true);
  });

  it("事件序列含 status/step/done/complete，且 done 前有 agent_settled", async () => {
    const { events, flow } = setup();
    await flow.run();
    const types = events.map((e) => e.type);
    expect(types[0]).toBe("status");
    expect(types).toContain("step");
    expect(types).toContain("done");
    expect(types.at(-1)).toBe("complete");
    expect(types).toContain("barrier");
    expect(types).toContain("stage");
    expect(types).toContain("lifecycle");
    const settled = events.filter((e) => e.type === "lifecycle" && (e as any).state === "agent_settled");
    expect(settled.length).toBeGreaterThan(0);
    // agent_end 不产生 done
    expect(events.filter((e) => e.type === "done").length).toBeGreaterThan(0);
  });

  it("续跑：基于会话日志回放已完成调用、接着跑中断的，P3/P4 仍覆盖全部模型", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-resume-"));
    const ws = prepareWorkspace({ root, sessionId: "r1", problem: "P" });
    const cfg = { ...DEFAULT_CONFIG, concurrency: 1 };
    // 第一次：评审 model_2 时进程被杀
    const ac = new AbortController();
    const first = journaling(new FakeAgentRunner({ models: MODELS }), (req) => {
      if (req.taskId === "P2-REVIEW:model_2") { ac.abort(); return true; }
      return false;
    });
    const s1 = await new SolveXFlow({ runner: first, bus: new EventBus(), ws, config: cfg,
      problem: "P", dataInfo: "" }).run(ac.signal);
    expect(s1.status).toBe("aborted");

    // 第二次：同一工作区、全新进程，流水线从头执行，编排层不做任何按模型的跳过
    const inner = new FakeAgentRunner({ models: MODELS });
    const second = journaling(inner);
    const bus = new EventBus(); const events: SolveXEvent[] = []; bus.subscribe((e) => events.push(e));
    const s2 = await new SolveXFlow({ runner: second, bus, ws, config: cfg, problem: "P", dataInfo: "" }).run();
    expect(s2.status).toBe("completed");
    // 只有中断点之后的调用真正打到模型
    expect(inner.calls.map((c) => c.taskId)).toEqual(["P2-REVIEW:model_2", "P2-REVIEW:model_3", "P4"]);
    const replayed = events.filter((e: any) => e.type === "info" && /replayed from session journal/.test(e.message));
    expect(replayed.map((e: any) => e.taskId)).toEqual(
      expect.arrayContaining(["P2-IMPL:model_1", "P2-IMPL:model_2", "P2-IMPL:model_3", "P2-REVIEW:model_1"]));
    // 旧策略的 bug：被跳过的模型从汇总和论文里消失
    const agg = readFileSync(join(ws.paths.programming, "all_results_summary.md"), "utf-8");
    for (const m of MODELS) expect(agg).toContain(`## ${m}`);
    expect(s2.models.map((m) => m.name)).toEqual(MODELS);
  });

  it("续跑一个已经跑完的工作区（含评审→修复→复审）：全部回放，不发起任何新的模型调用（r7 续跑实测回归）", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-replay-"));
    const ws = prepareWorkspace({ root, sessionId: "rp", problem: "P" });
    const cfg = { ...DEFAULT_CONFIG, concurrency: 3 };
    const NEEDS = `${FAKE_REVIEW_BODY}VERIFICATION_RESULT: NEEDS_REVISION\n## Issues Found:\n1. x\n## Fix Instructions:\nredo`;
    // 评审：第 1、2 轮要求修改，第 3 轮通过 → 两次修复、最新评审文件被每轮覆盖
    const reviewer = (req: any): FakeOutcome | undefined => {
      if (req.role !== "review") return undefined;
      const round = Number(req.journal.path.match(/review-(\d)\.jsonl$/)[1]);
      return { text: round < 3 ? NEEDS : FAKE_REVIEW_OK, files: {} };
    };
    const first = journaling(new FakeAgentRunner({ models: MODELS, handlers: [reviewer] }));
    expect((await new SolveXFlow({ runner: first, bus: new EventBus(), ws, config: cfg, problem: "P", dataInfo: "" }).run()).status).toBe("completed");
    await new Promise((r) => setTimeout(r, 20));                     // 让回放时的写入时间晚于首轮
    const inner = new FakeAgentRunner({ models: MODELS, handlers: [reviewer] });
    const s2 = await new SolveXFlow({ runner: journaling(inner), bus: new EventBus(), ws, config: cfg, problem: "P", dataInfo: "" }).run();
    expect(s2.status).toBe("completed");
    expect(inner.calls.map((c) => `${c.taskId}/${c.journal?.call}`)).toEqual([]);
  });

  it("skipToWriting：只执行 P3(纯代码) + P4", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-skip-"));
    const ws = prepareWorkspace({ root, sessionId: "w1", problem: "P" });
    writeFileSync(join(ws.paths.modeling, "master_plan.md"), "## Model 1: A\n");
    const runner = new FakeAgentRunner();
    const bus = new EventBus();
    const flow = new SolveXFlow({ runner, bus, ws, config: DEFAULT_CONFIG,
      problem: "P", dataInfo: "", skipToWriting: true });
    await flow.run();
    expect(runner.calls.map((c) => c.role)).toEqual(["writing"]);
    expect(existsSync(join(ws.paths.programming, "all_results_summary.md"))).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
  });

  it("AbortSignal 触发后状态为 aborted，已落盘产物不损坏", async () => {
    const ac = new AbortController();
    const runner = new FakeAgentRunner({ models: MODELS, onCall: (r) => { if (r.taskId?.startsWith("P2-IMPL")) ac.abort(); } });
    const { ws, bus, flow } = setup({ runner });
    const summary = await flow.run(ac.signal);
    expect(summary.status).toBe("aborted");
    expect(existsSync(join(ws.paths.modeling, "master_plan.md"))).toBe(true);
  });

  it("D4：strict 模式下 Critical 问题阻断进入 P4", async () => {
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (req) => req.taskId?.startsWith("P2-IMPL") ? { text: "ok", files: {} } : undefined,
    ] });
    const { ws, flow } = setup({ strict: true, runner });
    const summary = await flow.run();
    expect(summary.status).toBe("failed");
    expect(summary.issues.some((i) => i.severity === "critical")).toBe(true);
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(false);
  });

  it("非 strict 下 Critical 只 warn，仍进入 P4", async () => {
    const runner = new FakeAgentRunner({ models: ["Model 1"], handlers: [
      (req) => req.taskId?.startsWith("P2-IMPL") ? { text: "ok", files: {} } : undefined,
    ] });
    const { ws, flow } = setup({ strict: false, runner });
    const summary = await flow.run();
    expect(summary.status).toBe("completed");
    expect(existsSync(join(ws.paths.paper, "main.tex"))).toBe(true);
  });
});

describe("用量核算（真实模型实测回归）", () => {
  it("同一 taskId 多次调用累加 usage（含 cacheRead），P4 缺 main.tex 时如实失败", async () => {
    const base = new FakeAgentRunner({ models: MODELS });
    let p4Calls = 0;
    const runner = {
      calls: base.calls,
      async run(req: any, signal?: AbortSignal) {
        if (req.taskId === "P4") { p4Calls++; return { text: "", artifacts: [], settled: true,
          usage: { input: 10, output: 5, cacheRead: 90, cost: 0 } }; }      // 不写 main.tex
        const r = await base.run(req, signal);
        return { ...r, usage: { input: 100, output: 50, cacheRead: 400, cost: 0 } };
      },
    } as any;
    const { flow } = setup({ runner });
    const summary = await flow.run();
    expect(p4Calls).toBe(6);                                       // 首次 + 5 次催促（ADR-0014）
    expect(summary.status).toBe("failed");                         // 产物门：没有论文不能报 completed
    const p1 = summary.usageByTask["P1"] as any;
    expect(p1.input + p1.cacheRead + p1.output).toBe(550);
    expect((summary.usageByTask["P4"] as any).cacheRead).toBe(540);
    const calls = Object.values(summary.usageByTask).reduce((a: number, u: any) => a + u.calls, 0);
    expect(summary.totalTokens).toBe((calls - 6) * 550 + 6 * 105); // 每次调用都计入，不被覆盖
  });
});

describe("交叉评审结论（真实模型实测回归）", () => {
  /** reviewText(model, round) 决定每轮评审输出；默认不写任何文件（评审是只读的）。 */
  function reviewRunner(reviewText: (dir: string, round: number) => string,
                        onFix?: (req: any) => FakeOutcome | undefined) {
    const base = new FakeAgentRunner({ models: MODELS });
    const reviews: any[] = [], fixes: any[] = [];
    const runner = {
      calls: base.calls,
      async run(req: any, signal?: AbortSignal) {
        if (req.role === "review") {
          base.calls.push(req); reviews.push(req);
          const round = Number(req.journal.path.match(/review-(\d)\.jsonl$/)[1]);
          const text = reviewText(req.taskId.split(":")[1], round);
          const submitted = await fakeSubmit(req, text);      // 评审把同一份内容交给 submit_review
          return { text, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 },
                   ...(submitted ? { submitted } : {}) };
        }
        if (/^fix-\d$/.test(req.journal?.call ?? "")) {
          fixes.push(req);
          const o = onFix?.(req);
          if (o) { base.calls.push(req); for (const [rel, c] of Object.entries(o.files ?? {})) writeFileSync(join(req.cwd, rel), c);
                   const submitted = await fakeSubmit(req, o.text ?? "", o.submit);
                   return { text: o.text ?? "", artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 },
                            ...(submitted ? { submitted } : {}) }; }
        }
        return base.run(req, signal);
      },
    } as any;
    return { runner, reviews, fixes, base };
  }
  const NEEDS = (fix: string) => `${FAKE_REVIEW_BODY}Numbers off.\nVERIFICATION_RESULT: NEEDS_REVISION\n## Issues Found:\n1. sum=60\n## Fix Instructions:\n${fix}`;

  it("只读评审：从评审输出解析结论、逐轮落盘；修复意见发进该模型的实现会话，不另开修复 Agent", async () => {
    const { runner, fixes, reviews } = reviewRunner((d, r) => r === 1 ? NEEDS(`normalize-${d}`) : FAKE_REVIEW_OK);
    const { flow, events, ws } = setup({ runner });
    const s = await flow.run();
    expect(fixes.length).toBe(3);
    for (const f of fixes) {
      const d = f.taskId.split(":")[1];
      expect(f.taskId).toBe(`P2-IMPL:${d}`);                                   // 沿用实现节点
      expect(f.journal).toEqual({ path: expect.stringMatching(new RegExp(`P2-IMPL_${d}\\.jsonl$`)), call: "fix-1" });
      expect(f.submit?.name).toBe("submit_fix");
      expect(f.task).toContain(`normalize-${d}`);
      expect(f.task).not.toContain("Test problem");                            // 题面已在会话上下文里，不重复
      expect(f.writablePrefixes).toEqual([`02_programming/${d}/`]);
      // 修复前，本轮评审已代为落盘
      expect(readFileSync(join(ws.paths.modeling, `${d}_review_r1.md`), "utf-8")).toContain("NEEDS_REVISION");
    }
    expect(reviews.length).toBe(6);                                            // 每个模型 2 轮
    expect(events.some((e: any) => e.type === "info" && /round 1 verdict = needs_revision/.test(e.message))).toBe(true);
    expect(s.models.every((m) => m.verdict === "satisfied" && m.reviewRounds === 2)).toBe(true);
    // 评审：system prompt 是角色说明，任务内容只发一次
    for (const r of reviews) {
      expect(r.systemPrompt).not.toBe(r.task);
      expect(r.systemPrompt).not.toContain("PROGRAMMER'S RESULTS REPORT");
      expect(r.task).toContain("PROGRAMMER'S RESULTS REPORT");
    }
  });

  it("最多评审 3 次：第 3 次修复后直接放行；每轮只带本轮意见，上一轮的丢弃", async () => {
    const { runner, fixes, reviews } = reviewRunner((d, r) => NEEDS(`instr-${d}-round${r}`));
    const { flow, events } = setup({ runner });
    const s = await flow.run();
    expect(reviews.length).toBe(9);                                            // 3 模型 × 3 轮，没有第 4 次评审
    expect(fixes.length).toBe(9);
    for (const f of fixes) {
      const round = Number(f.journal.call.split("-")[1]);
      expect(f.task).toContain(`round${round}`);
      for (const other of [1, 2, 3].filter((x) => x !== round)) expect(f.task).not.toContain(`round${other}`);
      expect(f.task).toContain(`ROUND ${round}/3`);
    }
    expect(events.filter((e: any) => e.type === "info" && /released after 3 review rounds/.test(e.message)).length).toBe(3);
    expect(s.models.every((m) => m.reviewRounds === 3)).toBe(true);
    expect(s.status).toBe("completed");
  });

  it("修复只改了代码、没更新 results_summary.md：submit_fix 不接受，在同一实现会话里催它补上（ADR-0015）", async () => {
    const { runner, base } = reviewRunner((_d, r) => r === 1 ? NEEDS("x") : FAKE_REVIEW_OK, (req) => {
      const d = req.taskId.split(":")[1];
      return { text: "patched code only", files: { [`02_programming/${d}/model.py`]: "print('patched')\n" } };
    });
    const { flow, events } = setup({ runner });
    await flow.run();
    const nudges = base.calls.filter((c) => c.journal?.call === "fix-1-submit-1");
    expect(nudges.length).toBe(3);
    for (const n of nudges) { expect(n.journal!.path).toMatch(/P2-IMPL_model_\d\.jsonl$/); expect(n.task).toContain("submit_fix"); }
    expect(base.calls.some((c) => c.journal?.call === "fix-1-summary")).toBe(false);   // 摘要已在催促后更新
    expect(events.filter((e: any) => e.type === "info" && /fix accepted \(fix-1, changed .*results_summary\.md/.test(e.message)).length).toBe(3);
  });

  it("实现方认为评审意见不对、选择不改：说明理由后直接接受，不催、不补摘要，记录「no files changed」", async () => {
    const decline = (req: any): FakeOutcome | undefined => /^fix-1/.test(req.journal?.call ?? "")
      ? { text: "No change needed.", files: {}, submit: { summary: "The reviewer compared shares from different weeks; the numbers are correct." } }
      : undefined;
    const base = new FakeAgentRunner({ models: MODELS, handlers: [decline] });
    const runner = { calls: base.calls, async run(req: any, sig?: AbortSignal) {
      if (req.role !== "review") return base.run(req, sig);
      base.calls.push(req);
      const round = Number(req.journal.path.match(/review-(\d)\.jsonl$/)[1]);
      const text = round === 1 ? NEEDS("recompute") : FAKE_REVIEW_OK;
      const submitted = await fakeSubmit(req, text);
      return { text, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 }, ...(submitted ? { submitted } : {}) };
    } } as any;
    const { flow, events } = setup({ runner });
    await flow.run();
    const m1 = base.calls.filter((c) => c.taskId === "P2-IMPL:model_1" && /^fix-1/.test(c.journal?.call ?? ""));
    expect(m1.map((c) => c.journal!.call)).toEqual(["fix-1"]);
    expect(m1[0].task).toContain("you may leave that part unchanged");
    expect(events.filter((e: any) => e.type === "info" && /fix accepted \(fix-1, no files changed\): The reviewer compared/.test(e.message)).length).toBe(3);
  });

  it("修复改了代码却没更新摘要、催满也没交：告警并走摘要补写兜底", async () => {
    const lazy = (req: any): FakeOutcome | undefined => {
      if (!/^fix-1/.test(req.journal?.call ?? "") || req.journal?.call === "fix-1-summary") return undefined;
      const d = req.taskId.split(":")[1];
      return { text: "patched", files: { [`02_programming/${d}/model.py`]: `print('${req.journal.call}')\n` } };
    };
    const base = new FakeAgentRunner({ models: MODELS, handlers: [lazy] });
    const runner = { calls: base.calls, async run(req: any, sig?: AbortSignal) {
      if (req.role !== "review") return base.run(req, sig);
      base.calls.push(req);
      const round = Number(req.journal.path.match(/review-(\d)\.jsonl$/)[1]);
      const text = round === 1 ? NEEDS("recompute") : FAKE_REVIEW_OK;
      const submitted = await fakeSubmit(req, text);
      return { text, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 }, ...(submitted ? { submitted } : {}) };
    } } as any;
    const { flow, events } = setup({ runner });
    await flow.run();
    const m1 = base.calls.filter((c) => c.taskId === "P2-IMPL:model_1" && /^fix-1/.test(c.journal?.call ?? ""));
    expect(m1.map((c) => c.journal!.call)).toEqual(["fix-1", "fix-1-submit-1", "fix-1-submit-2", "fix-1-summary"]);
    expect(events.filter((e: any) => e.type === "warn" && /fix-1 ended without an accepted submit_fix \(changed model\.py\)/.test(e.message)).length).toBe(3);
  });

  it("评审漏了结论行：submit_review 不接受，同一评审会话催它提交；始终没提交但列了问题 → 按 NEEDS_REVISION 修复（r5 实测回归）", async () => {
    const noVerdict = FAKE_REVIEW_BODY + "### Verdict\nFails numerically.\n## Issues Found:\n1. bad\n## Fix Instructions:\nredo-it";
    // model_1：催一次后提交 NEEDS_REVISION；model_2：两次催促都没提交；model_3：正常
    const { runner, reviews, fixes } = reviewRunner((d, r) =>
      r > 1 ? FAKE_REVIEW_OK : d === "model_3" ? FAKE_REVIEW_OK : noVerdict);
    const wrapped = { calls: runner.calls, async run(req: any, sig?: AbortSignal) {
      if (req.role === "review" && /^submit-\d$/.test(req.journal?.call ?? "")) {
        reviews.push(req);
        const d = req.taskId.split(":")[1];
        const text = d === "model_1" ? `${noVerdict}\nVERIFICATION_RESULT: NEEDS_REVISION` : "I already said it fails.";
        const submitted = await fakeSubmit(req, text);
        return { text, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 }, ...(submitted ? { submitted } : {}) };
      }
      return runner.run(req, sig);
    } } as any;
    const { flow, ws, events } = setup({ runner: wrapped });
    await flow.run();
    const asks = reviews.filter((r) => /^submit-/.test(r.journal.call));
    expect(asks.map((r) => `${r.taskId}/${r.journal.call}`).sort()).toEqual(
      ["P2-REVIEW:model_1/submit-1", "P2-REVIEW:model_2/submit-1", "P2-REVIEW:model_2/submit-2"]);
    for (const a of asks) { expect(a.journal.path).toMatch(/review-1\.jsonl$/); expect(a.task).toContain("submit_review"); }
    expect(fixes.map((f) => f.taskId).sort()).toEqual(["P2-IMPL:model_1", "P2-IMPL:model_2"]);
    for (const f of fixes) expect(f.task).toContain("redo-it");
    expect(readFileSync(join(ws.paths.modeling, "model_1_review_r1.md"), "utf-8")).toMatch(/VERIFICATION_RESULT: NEEDS_REVISION\n$/);
    expect(events.some((e: any) => e.type === "warn" && /Model 2: review round 1 never got an accepted submit_review/.test(e.message))).toBe(true);
  });

  it("评审以空回复或只有结论行结束：submit_review 不接受，催它提交书面评审，结论取自提交（r6 实测回归）", async () => {
    // model_1：空回复 → 提交 NEEDS_REVISION；model_2：只有结论行 → 提交 SATISFIED；model_3：正常
    const { runner, reviews, fixes } = reviewRunner((d, r) =>
      r > 1 || d === "model_3" ? FAKE_REVIEW_OK : d === "model_1" ? "" : "VERIFICATION_RESULT: SATISFIED");
    const wrapped = { calls: runner.calls, async run(req: any, sig?: AbortSignal) {
      if (req.role === "review" && req.journal?.call === "submit-1") {
        reviews.push(req);
        const d = req.taskId.split(":")[1];
        const text = d === "model_1" ? `${FAKE_REVIEW_BODY}VERIFICATION_RESULT: NEEDS_REVISION\n## Issues Found:\n1. off\n## Fix Instructions:\nrecompute-share`
                                     : FAKE_REVIEW_OK;
        const submitted = await fakeSubmit(req, text);
        return { text, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 }, ...(submitted ? { submitted } : {}) };
      }
      return runner.run(req, sig);
    } } as any;
    const { flow, ws, events } = setup({ runner: wrapped });
    await flow.run();
    const asks = reviews.filter((r) => r.journal.call === "submit-1");
    expect(asks.map((r) => r.taskId).sort()).toEqual(["P2-REVIEW:model_1", "P2-REVIEW:model_2"]);
    expect(fixes.map((f) => f.taskId)).toEqual(["P2-IMPL:model_1"]);
    expect(fixes[0].task).toContain("recompute-share");
    expect(readFileSync(join(ws.paths.modeling, "model_2_review_r1.md"), "utf-8")).toContain("Checked:");
    expect(events.filter((e: any) => e.type === "warn" && /ended without calling submit_review/.test(e.message)).length).toBe(2);
    // 评审请求带提交工具
    for (const r of reviews) expect(r.submit?.name).toBe("submit_review");
  });

  it("不再有 provisional 机制：P3 汇总与 P4 不包含评审状态", async () => {
    const { runner, base } = reviewRunner((d) => NEEDS(`fix-${d}`));
    const { flow, ws } = setup({ runner });
    await flow.run();
    const agg = readFileSync(join(ws.paths.programming, "all_results_summary.md"), "utf-8");
    expect(agg).not.toMatch(/Cross-review|provisional|Verdict:/i);
    const paper = base.calls.find((c) => c.taskId === "P4")!;
    expect(paper.task).not.toMatch(/Cross-review|provisional|Verdict:/i);
  });
  it("评审提示词追加运行时说明（可跑代码、改动会被还原、由 SolveX 代存），逐字保留的 review.md 资产不变", () => {
    const out = renderReview({ model_name: "M", problem: "P", model_plan: "X", results: "R", review_path: "/tmp/r.md" });
    expect(out).toContain("You MAY run code to verify the");
    expect(out).toContain("reverted automatically");
    expect(out).toContain("call the\n`submit_review` tool");
    expect(out).toContain("your reply text is not saved");
  });
});

describe("题面按阶段生效（真实模型实测回归：P1 专用约束泄漏到 P2/P4）", () => {
  const problem = "# Problem\n<!-- solvex:phase P1 -->\n- FIRST write master_plan.md, then stop.\n<!-- /solvex:phase -->\nPredict votes.\n";
  it("scopeProblem：标记段只给列出的阶段，标记本身去掉；下游追加说明", () => {
    expect(scopeProblem(problem, "P1")).toBe("# Problem\n- FIRST write master_plan.md, then stop.\nPredict votes.\n");
    const p2 = scopeProblem(problem, "P2");
    expect(p2).not.toContain("FIRST write master_plan.md");
    expect(p2).not.toContain("solvex:phase");
    expect(p2).toContain("Predict votes.");
    expect(p2.endsWith(DOWNSTREAM_PROBLEM_NOTE)).toBe(true);
    expect(scopeProblem("<!-- solvex:phase P1, P4 -->X<!-- /solvex:phase -->", "P4")).toContain("X");
  });
  it("流水线：P1 看得到 P1 专用约束，IMPL / 评审 / 修复 / P4 看不到", async () => {
    const root = mkdtempSync(join(tmpdir(), "solvex-scope-"));
    const ws = prepareWorkspace({ root, sessionId: "s1", problem });
    const runner = new FakeAgentRunner({ models: MODELS });
    await new SolveXFlow({ runner, bus: new EventBus(), ws, config: { ...DEFAULT_CONFIG, concurrency: 3 },
      problem, dataInfo: "" }).run();
    const p1 = runner.calls.find((c) => c.taskId === "P1")!;
    expect(p1.task).toContain("FIRST write master_plan.md");
    const downstream = runner.calls.filter((c) => c.taskId !== "P1");
    expect(downstream.length).toBeGreaterThan(3);
    for (const c of downstream) {
      expect(c.task).not.toContain("FIRST write master_plan.md");
      expect(c.task).toContain("Predict votes.");
    }
  });
});

describe("ADR-0014：规划节点建共享数据集、复现门禁、评审可跑代码", () => {
  it("P1 没建共享数据集：在同一规划会话里催它接着做；建好后 IMPL 提示附上数据集说明", async () => {
    let asked = false;
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req) => {
      if (req.taskId === "P1" && req.journal?.call === "plan")      // 首次只写计划
        return { text: "plan", files: { "01_modeling/master_plan.md": "## Model 1: A\n## Model 2: B\n## Model 3: C\n" } };
      if (req.journal?.call === "plan-continue-1") {                // 走默认：建共享数据集
        asked = true;
        expect(req.task).toContain("01_modeling/shared_data/data_dictionary.md");
        expect(req.task).not.toContain("master plan at");             // 计划已有，不再要求
        return undefined;
      }
      return undefined;
    }] });
    const { flow } = setup({ runner });
    await flow.run();
    expect(asked).toBe(true);
    const impl = runner.calls.find((c) => c.taskId === "P2-IMPL:model_1")!;
    expect(impl.task).toContain("SHARED DATASET (prepared and validated in Phase 1)");
    expect(impl.task).toMatch(/01_modeling\/shared_data\/ — read data_dictionary\.md/);
  });

  it("共享数据集 P1 之后只读：实现会话改了就还原并告警", async () => {
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req) =>
      req.taskId === "P2-IMPL:model_2" && req.journal?.call === "impl"
        ? { text: "VERIFICATION_RESULT: SATISFIED", files: {
            "01_modeling/shared_data/panel.csv": "corrupted\n",
            "02_programming/model_2/run.py": "import json\njson.dump({'v': 1}, open('results.json','w'))\n",
            "02_programming/model_2/results.json": "{\"v\": 1}",
            "02_programming/model_2/results_summary.md": "# s\n## Key Numerical Results\nv=1\n",
            "02_programming/model_2/figures/f.png": "png" } }
        : undefined] });
    const { flow, ws, events } = setup({ runner });
    await flow.run();
    expect(readFileSync(join(ws.paths.modeling, "shared_data/panel.csv"), "utf-8")).toContain("season,week");
    expect(events.some((e: any) => e.type === "warn" && /Phase-1 artifacts are read-only after Phase 1: reverted/.test(e.message))).toBe(true);
  });

  it("复现失败：结果发回该模型的实现会话，修好后通过；一直失败则最多修 2 次后告警放行", async () => {
    const seen: Record<string, number> = {};
    const reproduce = async (dir: string) => {
      const m = dir.split("/").pop()!; seen[m] = (seen[m] ?? 0) + 1;
      if (m === "model_1" && seen[m] === 1) return { ok: false, reason: "re-running run.py produced different results",
                                                      mismatches: ["agreement: delivered 0.8681, re-run produced 0.2956"], ms: 5 };
      if (m === "model_2") return { ok: false, reason: "python3 run.py exited with code 1:\nNameError", ms: 5 };
      return { ok: true, ms: 5 };
    };
    const runner = new FakeAgentRunner({ models: MODELS });
    const root = mkdtempSync(join(tmpdir(), "solvex-repro-flow-"));
    const ws = prepareWorkspace({ root, sessionId: "rp", problem: "P" });
    const bus = new EventBus(); const events: SolveXEvent[] = []; bus.subscribe((e) => events.push(e));
    await new SolveXFlow({ runner, bus, ws, config: { ...DEFAULT_CONFIG, concurrency: 3 }, problem: "P", dataInfo: "",
      reproduce }).run();
    const fixes = runner.calls.filter((c) => c.journal?.call?.startsWith("repro-"));
    const m1 = fixes.filter((c) => c.taskId === "P2-IMPL:model_1");
    expect(m1.map((c) => c.journal!.call)).toEqual(["repro-impl-1"]);
    expect(m1[0].journal!.path).toMatch(/P2-IMPL_model_1\.jsonl$/);        // 发进实现会话
    expect(m1[0].task).toContain("agreement: delivered 0.8681, re-run produced 0.2956");
    expect(fixes.filter((c) => c.taskId === "P2-IMPL:model_2").map((c) => c.journal!.call)).toEqual(["repro-impl-1", "repro-impl-2"]);
    expect(events.some((e: any) => e.type === "warn" && /model_2|Model 2/.test(e.message) && /reproduction failed after 2 fix attempts/.test(e.message))).toBe(true);
    expect(events.some((e: any) => e.type === "done" && /Model 1: reproduction passed \(impl/.test(e.message))).toBe(true);
  });

  it("评审可以跑代码，但对实现、共享数据集、master_plan 的改动全部还原；草稿目录不受影响", async () => {
    const base = new FakeAgentRunner({ models: MODELS });
    const runner = { calls: base.calls, async run(req: any, sig?: AbortSignal) {
      if (req.role !== "review") return base.run(req, sig);
      base.calls.push(req);
      const d = req.taskId.split(":")[1];
      writeFileSync(join(req.cwd, "02_programming", d, "run.py"), "print('reviewer edited')\n");
      writeFileSync(join(req.cwd, "02_programming", d, "extra.csv"), "x\n");
      writeFileSync(join(req.cwd, "01_modeling/master_plan.md"), "overwritten");
      mkdirSync(join(req.cwd, ".solvex/scratch"), { recursive: true });
      writeFileSync(join(req.cwd, ".solvex/scratch", `${d}.py`), "scratch\n");
      return { text: FAKE_REVIEW_OK, artifacts: [], settled: true, usage: { input: 1, output: 1, cost: 0 },
               submitted: await fakeSubmit(req, FAKE_REVIEW_OK) };
    } } as any;
    const { flow, ws, events } = setup({ runner });
    await flow.run();
    for (const d of ["model_1", "model_2", "model_3"]) {
      expect(readFileSync(join(ws.paths.programming, d, "run.py"), "utf-8")).toContain("json.dump");
      expect(existsSync(join(ws.paths.programming, d, "extra.csv"))).toBe(false);
      expect(existsSync(join(ws.dir, ".solvex/scratch", `${d}.py`))).toBe(true);
    }
    expect(readFileSync(join(ws.paths.modeling, "master_plan.md"), "utf-8")).toContain("## Model 1");
    expect(events.filter((e: any) => e.type === "warn" && /Reverted changes made during review/.test(e.message)).length).toBe(3);
    expect(events.some((e: any) => e.type === "warn" && /Phase-1 artifacts are read-only.*master_plan\.md/.test(e.message))).toBe(true);
    const reviews = base.calls.filter((c) => c.role === "review");
    for (const r of reviews) expect(r.tools).toEqual(expect.arrayContaining(["python_execute", "bash"]));
  });
});

describe("交付物门禁：模型提前结束本轮时在同一会话里催它接着做（r6 实测回归）", () => {
  it("P1 两次提前停下：继续催，第 3 次交齐；IMPL 缺 run.py/results.json 也会被催", async () => {
    let p1 = 0;
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req): FakeOutcome | undefined => {
      if (req.taskId === "P1" && (req.journal?.call === "plan" || /continue-[12]$/.test(req.journal?.call ?? ""))) {
        p1++; return { text: "Let me rewrite prep_data.py more carefully.", files: {} };   // 说完就停
      }
      if (req.taskId === "P2-IMPL:model_1" && req.journal?.call === "impl")
        return { text: "done", files: { "02_programming/model_1/results_summary.md": "# s\n", "02_programming/model_1/figures/f.png": "x" } };
      return undefined;
    }] });
    const { flow, events } = setup({ runner });
    const s = await flow.run();
    expect(s.status).toBe("completed");
    expect(p1).toBe(3);
    const nudges = runner.calls.filter((c) => /-continue-\d$/.test(c.journal?.call ?? ""));
    expect(nudges.filter((c) => c.taskId === "P1").map((c) => c.journal!.call)).toEqual(["plan-continue-1", "plan-continue-2", "plan-continue-3"]);
    const m1 = nudges.filter((c) => c.taskId === "P2-IMPL:model_1");
    expect(m1.map((c) => c.journal!.call)).toEqual(["impl-continue-1"]);
    expect(m1[0].task).toMatch(/model_1\/run\.py/);
    expect(m1[0].task).toMatch(/model_1\/results\.json/);
    expect(m1[0].task).toContain("do not start over");
    expect(events.filter((e: any) => e.type === "warn" && /stopped before finishing/.test(e.message)).length).toBe(4);
  });
  it("P1 催满仍没有计划 → MasterPlanError", async () => {
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req) =>
      req.taskId === "P1" ? { text: "thinking...", files: {} } : undefined] });
    const { flow } = setup({ runner });
    await expect(flow.run()).rejects.toThrow(/MasterPlanError: no master plan after the planning call and 4 continuation requests/);
    expect(runner.calls.filter((c) => c.taskId === "P1").length).toBe(5);
  });
  it("P4 只写了引言和 Model 1 就停下：submit_paper 不接受，列出缺的部分接着写，直到论文完整（r6 实测回归）", async () => {
    const half = "\\documentclass{article}\\begin{document}\n\\section{Introduction}\n\\section{Model 1: A}\n\\end{document}\n";
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req): FakeOutcome | undefined =>
      req.taskId === "P4" && req.journal?.call === "paper" ? { text: "", files: { "04_paper/main.tex": half } } : undefined] });
    const { flow, events, ws } = setup({ runner });
    const s = await flow.run();
    expect(s.status).toBe("completed");
    const p4 = runner.calls.filter((c) => c.taskId === "P4");
    expect(p4.map((c) => c.journal!.call)).toEqual(["paper", "paper-submit-1"]);
    expect(p4[0].submit?.name).toBe("submit_paper");
    expect(p4[0].task).toContain("call the `submit_paper` tool");
    expect(p4[1].task).toMatch(/Model 2/);
    expect(p4[1].task).toMatch(/Model 3/);
    expect(p4[1].task).toMatch(/Conclusion/);
    expect(p4[1].task).not.toMatch(/Model 1 \(/);
    expect(readFileSync(join(ws.paths.paper, "main.tex"), "utf-8")).toContain("Model 3");
    expect(events.some((e: any) => e.type === "warn" && /P4: ended without calling submit_paper/.test(e.message))).toBe(true);
  });

  it("题面要求备忘录：备忘录是 submit_paper 的必填参数，太短不接受；接受后写成 memo.tex 插进论文（r6：没写备忘录）", async () => {
    const problem = "Write a paper and include a one-page memo to the producers.";
    const noMemoPaper = (n: number) => "\\documentclass{article}\n\\begin{document}\n\\begin{abstract}\n" + "Abstract text. ".repeat(30) +
      "\n\\end{abstract}\n" + Array.from({ length: n }, (_, i) => `\\section{Model ${i + 1}: X}\n`).join("") +
      "\\section{Conclusion}\nDone.\n\\end{document}\n";
    const runner = new FakeAgentRunner({ models: MODELS, handlers: [(req): FakeOutcome | undefined => {
      if (req.taskId !== "P4") return undefined;
      return req.journal?.call === "paper"
        ? { text: "Paper done.", files: { "04_paper/main.tex": noMemoPaper(3) }, submit: { memo: "Dear producers, keep it." } }
        : { text: "Submitted.", files: {} };                  // 催促后按默认参数提交完整备忘录
    }] });
    const root = mkdtempSync(join(tmpdir(), "solvex-memo-"));
    const ws = prepareWorkspace({ root, sessionId: "memo", problem });
    const bus = new EventBus(); const events: SolveXEvent[] = []; bus.subscribe((e) => events.push(e));
    const s = await new SolveXFlow({ runner, bus, ws, config: { ...DEFAULT_CONFIG, concurrency: 3 }, problem, dataInfo: "" }).run();
    expect(s.status).toBe("completed");
    const p4 = runner.calls.filter((c) => c.taskId === "P4");
    expect(p4.map((c) => c.journal!.call)).toEqual(["paper", "paper-submit-1"]);
    expect(p4[0].task).toContain("`memo` argument");
    expect(p4[0].submit!.parameters.required).toEqual(["memo"]);
    const tex = readFileSync(join(ws.paths.paper, "main.tex"), "utf-8");
    expect(tex).toMatch(/\\input\{memo\}\n\\end\{document\}/);
    expect(readFileSync(join(ws.paths.paper, "memo.tex"), "utf-8")).toMatch(/\\section\*\{Memorandum: To the Producers\}/);
    expect(events.some((e: any) => e.type === "warn" && /submit_paper never accepted/.test(e.message))).toBe(false);
  });
});
