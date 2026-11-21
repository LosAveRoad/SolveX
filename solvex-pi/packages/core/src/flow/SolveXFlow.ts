import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { AgentRunner, RunRequest, RunResult } from "../ports/AgentRunner.js";
import { DEFAULT_MAX_TURNS } from "../ports/AgentRunner.js";
import type { EventBus } from "../events/EventBus.js";
import type { Issue, Phase, RunSummary, StageNode, ThinkingLevel } from "../events/types.js";
import type { ModelConfig, PhaseKey } from "../config/schema.js";
import type { WorkspaceInfo } from "../workspace/index.js";
import { DIR, SCRATCH_DIR, SHARED_DATA_DIR, journalPath, modelDirName } from "../workspace/paths.js";
import { parseModels, sectionFor } from "../contracts/masterPlan.js";
import { scopeProblem, type ProblemPhase } from "../contracts/problemScope.js";
import { parseVerdict } from "../gates/parseVerdict.js";
import { validateModelOutput } from "../gates/validateModelOutput.js";
import { validateSummaryShape } from "../contracts/modelResult.js";
import { ensureSummary } from "../gates/ensureSummary.js";
import { reproduce as defaultReproduce, type ReproResult } from "../gates/reproduce.js";
import { captureFiles, changedFiles, fingerprint, restoreFiles, type FileSnapshot, type Fingerprint } from "../gates/fileGuard.js";
import { memoRequired, paperGaps } from "../gates/paperGate.js";
import {
  FIX_TOOL, PAPER_TOOL, REVIEW_TOOL, fixBaseline, fixSubmitTool, formatReview, paperSubmitTool,
  reviewSubmitTool, submitInstruction, submitNudge,
} from "../gates/submitTools.js";
import {
  modelingSystem, programmingSystem, writingSystem, reviewSystem, renderReview,
  renderPlan, renderImplement, renderSummaryRetry,
  renderRevision, renderReviewFix, renderReproFix, renderPaper, sharedDataNote,
  ROLE_TOOLS,
} from "../prompts/index.js";
import { buildDag, type DagNode } from "./dag.js";
import { schedule, type SchedTask } from "./scheduler.js";
import { aggregate, figureInfo } from "./stages.js";
import { initialState, upsertNode, type FlowState } from "./state.js";

export type SolveXFlowDeps = {
  runner: AgentRunner;
  bus: EventBus;
  ws: WorkspaceInfo;
  config: ModelConfig;
  problem: string;
  dataInfo?: string;
  skipToWriting?: boolean;
  modelsOverride?: string[];
  /** 复现门禁（默认在模型目录里重跑 python3 run.py）；测试可注入。 */
  reproduce?: (modelDir: string, opts: { signal?: AbortSignal }) => Promise<ReproResult>;
};

/** 每个模型最多评审 3 次；第 3 次修复之后直接放行。 */
export const MAX_REVIEW_ROUNDS = 3;

/** 复现门禁失败后最多发回实现会话修几次。 */
export const REPRO_MAX_FIXES = 2;

/** 交付物缺失时最多在同一会话里催几次（ADR-0014）。r6 实测：GLM 5.3 Flash 在多步任务里会说完
 *  "接下来我要……"就结束本轮、不调用工具（P1 两次都在 16 轮、4 轮时停下，预算是 60 轮）。 */
export const CONTINUE_NUDGES = { P1: 4, IMPL: 3 } as const;

/** 没有成功调用提交工具时，最多在同一会话里催几次（ADR-0015）。 */
export const SUBMIT_NUDGES = { REVIEW: 2, FIX: 2, P4: 5 } as const;

export const continueMessage = (missing: string[]): string =>
  "[SolveX] You ended your turn before the task was complete. These deliverables are still missing:\n" +
  missing.map((x) => `- ${x}`).join("\n") +
  "\nContinue from where you stopped — do not start over — and create them before you end your turn. " +
  "If a script failed, fix it and run it again.";

const writeIfChanged = (path: string, text: string): void => {
  if (!existsSync(path) || readFileSync(path, "utf-8") !== text) writeFileSync(path, text);
};

const reviewBody = (text: string): string =>
  text.replace(/VERIFICATION_RESULT:\s*(SATISFIED|NEEDS_REVISION)/gi, "").trim();

const PHASE_KEY: Partial<Record<string, PhaseKey>> = {
  P1: "P1", P3: "P3", P4: "P4",
};

/** 四阶段状态机（§5.2）。构造函数只接受 core 抽象，不 import 任何 Pi 符号。 */
export class SolveXFlow {
  private readonly state: FlowState = initialState();
  private p1Done = false;
  /** 计划里的模型（P3/P4 以它为准，而不是本次实际跑过的节点）。 */
  private models: string[] = [];
  constructor(private readonly deps: SolveXFlowDeps) {}

  /**
   * 断点续跑：每个 Agent 一份会话日志（session），会话里每次调用有一个语义化、确定的 call 名
   * （不是调用序号，因此重跑时某个兜底调用不再触发，后面的调用也不会错位）。
   * 重跑同一个工作区时整条流水线照常执行：已完成的调用从日志回放、不调用模型；
   * 中断的调用从日志接着跑；未开始的调用在该会话末尾继续。编排层不为每类 Agent 单独写续跑规则。
   */
  private journal(session: string, call: string): NonNullable<RunRequest["journal"]> {
    return { path: journalPath(this.deps.ws.dir, session), call };
  }

  private problem(phase: ProblemPhase): string { return scopeProblem(this.deps.problem, phase); }

  /** P1 的产物（共享数据集 + master_plan）在 P1 之后只读（ADR-0014）：只在 P1 结束后快照一次，
   *  任何会话改了都按这份快照还原。不能每次评审各拍一份：并行评审时后拍的快照会把别人的改动当成原样。 */
  private frozenSnapshot?: FileSnapshot;
  private sharedDir(): string { return join(this.deps.ws.dir, SHARED_DATA_DIR); }
  private hasSharedData(): boolean {
    const d = this.sharedDir();
    return existsSync(join(d, "data_dictionary.md")) && readdirSync(d).some((f) => /\.(csv|parquet|json)$/i.test(f));
  }
  private freezePhase1(): void {
    this.frozenSnapshot = captureFiles([this.sharedDir(), this.masterPlanPath()]);
  }
  private restorePhase1(taskId: string): void {
    if (!this.frozenSnapshot) return;
    const { restored, removed } = restoreFiles(this.frozenSnapshot, this.deps.ws.dir);
    if (restored.length || removed.length)
      this.deps.bus.warn(`Phase-1 artifacts are read-only after Phase 1: reverted ${[...restored, ...removed].join(", ")}`, 2, taskId);
  }

  /** 交付物门禁：会话结束时交付物不全，就在同一会话里告诉它还缺什么、让它接着做，最多 max 次。
   *  返回仍然缺失的交付物。call 名确定（`<prefix>-continue-<k>`），续跑时可回放。 */
  private async continueUntil(node: DagNode, role: RunRequest["role"], systemPrompt: string,
                              journal: { session: string; prefix: string }, missing: () => string[],
                              max: number, signal?: AbortSignal): Promise<string[]> {
    for (let k = 1; k <= max; k++) {
      const miss = missing();
      if (!miss.length) return [];
      this.deps.bus.warn(`${node.taskId}: stopped before finishing — missing ${miss.join(", ")}; asking it to continue (${k}/${max})`,
        node.phase, node.taskId);
      await this.call(this.baseReq(node, role, systemPrompt, continueMessage(miss),
        { session: journal.session, call: `${journal.prefix}-continue-${k}` }), signal);
    }
    return missing();
  }

  /** 提交门禁（ADR-0015）：调用结束时提交工具还没接受过提交，就在同一会话里催它补齐并提交，最多 max 次。
   *  hint 列出仍缺的部分，写进催促消息。返回被接受的提交参数（始终没有则 undefined）。 */
  private async nudgeSubmit(node: DagNode, tool: string, max: number, first: RunResult,
                            send: (msg: string, k: number) => Promise<RunResult>,
                            hint?: () => string[]): Promise<Record<string, unknown> | undefined> {
    let sub = first.submitted;
    for (let k = 1; !sub && k <= max; k++) {
      const miss = hint?.() ?? [];
      this.deps.bus.warn(`${node.taskId}: ended without calling ${tool}${miss.length ? ` — still missing ${miss.join(", ")}` : ""}; ` +
        `asking it to continue (${k}/${max})`, node.phase, node.taskId);
      sub = (await send(submitNudge(tool, miss), k)).submitted;
    }
    return sub;
  }

  /** 修复调用（评审修复 / 复现修复）都发进实现会话，以 submit_fix 结束。可以选择不改（说明理由）；
   *  改了哪些文件按修复请求发出时的指纹记录下来。 */
  private async fixCall(implNode: DagNode, m: string, absModelDir: string, task: string, call: string,
                        requireSummary: boolean, signal?: AbortSignal):
      Promise<{ r: RunResult; submitted?: Record<string, unknown>; changed: string[]; baseline: Fingerprint }> {
    const baseFile = journalPath(this.deps.ws.dir, implNode.taskId).replace(/\.jsonl$/, `.${call}.baseline.json`);
    const baseline = fixBaseline(baseFile, absModelDir);
    const submit = fixSubmitTool({ modelDir: absModelDir, baseline, requireSummary });
    const send = (t: string, c: string) => this.call({ ...this.baseReq(implNode, "programming", programmingSystem(), t,
      { session: implNode.taskId, call: c }), submit }, signal);
    const r = await send(task + submitInstruction(FIX_TOOL, "the fix is applied and the outputs are regenerated"), call);
    const submitted = await this.nudgeSubmit(implNode, FIX_TOOL, SUBMIT_NUDGES.FIX, r, (msg, k) => send(msg, `${call}-submit-${k}`));
    const changed = changedFiles(baseline, fingerprint(absModelDir));
    const what = changed.length ? `changed ${changed.join(", ")}` : "no files changed";
    if (submitted) this.deps.bus.info(`${m}: fix accepted (${call}, ${what}): ${String(submitted.summary ?? "").slice(0, 300)}`, 2, implNode.taskId);
    else this.deps.bus.warn(`${m}: ${call} ended without an accepted ${FIX_TOOL} (${what})`, 2, implNode.taskId);
    return { r, submitted, changed, baseline };
  }

  /** 复现门禁：重跑 run.py 并比对 results.json；失败就把结果发回该模型的实现会话，最多 REPRO_MAX_FIXES 次。 */
  private async reproGate(implNode: DagNode, m: string, absModelDir: string, tag: string,
                          signal?: AbortSignal): Promise<boolean> {
    const run = this.deps.reproduce ?? defaultReproduce;
    for (let k = 0; ; k++) {
      const r = await run(absModelDir, { signal });
      if (r.ok) { this.deps.bus.done(`${m}: reproduction passed (${tag}, ${(r.ms / 1000).toFixed(0)}s)`, 2, implNode.taskId); return true; }
      const detail = [r.reason ?? "unknown failure", ...(r.mismatches ?? []).slice(0, 20).map((x) => `- ${x}`),
        ...((r.mismatches?.length ?? 0) > 20 ? [`- …and ${r.mismatches!.length - 20} more`] : [])].join("\n");
      if (k >= REPRO_MAX_FIXES) {
        this.deps.bus.warn(`${m}: reproduction failed after ${k} fix attempts (${tag}): ${r.reason}`, 2, implNode.taskId);
        return false;
      }
      this.deps.bus.warn(`${m}: reproduction failed (${tag}): ${r.reason} — sending back to the implementation session`, 2, implNode.taskId);
      await this.fixCall(implNode, m, absModelDir,
        renderReproFix({ abs_model_dir: absModelDir, detail, attempt: k + 1, max_attempts: REPRO_MAX_FIXES }),
        `repro-${tag}-${k + 1}`, false, signal);
      this.restorePhase1(implNode.taskId);
    }
  }

  private nodeState(node: DagNode, state: StageNode["state"], extra: Partial<StageNode> = {}): void {
    const base: StageNode = {
      id: node.id, label: node.label, phase: node.phase,
      kind: node.kind === "barrier" ? "stage" : node.kind,
      state, dependsOn: node.dependsOn, taskId: node.taskId,
      ...(node.model ? { model: node.model } : {}), ...(node.role ? { role: node.role } : {}),
      ...(state === "running" ? { startedAt: Date.now() } : {}),
      ...(["done", "failed", "aborted", "skipped"].includes(state) ? { endedAt: Date.now() } : {}),
      ...extra,
    };
    upsertNode(this.state, base);
    this.deps.bus.stage(base);
  }

  private phaseConfig(node: DagNode): Pick<RunRequest, "model" | "thinkingLevel" | "scopedModels"> {
    const key = node.taskId.startsWith("P2-IMPL") ? "P2_IMPL"
      : node.taskId.startsWith("P2-REVIEW") ? "P2_REVIEW" : PHASE_KEY[node.taskId] ?? "P1";
    const c = this.deps.config.byPhase[key];
    return {
      ...(c?.provider && c?.model ? { model: { provider: c.provider, id: c.model } } : {}),
      thinkingLevel: (c?.thinkingLevel ?? this.deps.config.defaults.thinkingLevel) as ThinkingLevel,
      ...(this.deps.config.scopedModels.length ? { scopedModels: this.deps.config.scopedModels } : {}),
    };
  }

  private async call(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    const full: RunRequest = { ...req, tools: req.tools ?? ROLE_TOOLS[req.role],
      maxTurns: req.maxTurns ?? DEFAULT_MAX_TURNS[req.role],
      ...this.phaseConfig({ taskId: req.taskId ?? "P1" } as DagNode),
      onEvent: (e) => this.deps.bus.emit(e) };
    this.deps.bus.lifecycle(full.taskId ?? "unknown", "agent_start");
    this.deps.bus.emit({ type: "model", taskId: full.taskId, provider: full.model?.provider ?? "default",
      model: full.model?.id ?? "auto", thinkingLevel: full.thinkingLevel, ts: Date.now() });
    const tid = full.taskId ?? "unknown";
    // 同一 taskId 可能多次调用（摘要重试 / 修订 / 定向修复）：累加而非覆盖；失败调用的用量同样计入。
    const account = (u?: RunResult["usage"]) => {
      const a = (this.state.usageByTask[tid] ??= { input: 0, output: 0, cacheRead: 0, cost: 0, calls: 0 });
      a.calls++;
      if (!u) return;
      a.input += u.input; a.output += u.output; a.cacheRead += u.cacheRead ?? 0; a.cost += u.cost ?? 0;
    };
    try {
      const r = await this.deps.runner.run(full, signal);
      account(r.usage);
      if (r.replayed) this.deps.bus.info(`${tid}: replayed from session journal (no model call)`, full.phase ?? 2, tid);
      else if (r.resumed) this.deps.bus.info(`${tid}: resumed interrupted session from journal`, full.phase ?? 2, tid);
      if (r.turnCapped)
        this.deps.bus.warn(`${tid}: hit maxTurns=${full.maxTurns}; session truncated`, full.phase ?? 2, tid);
      if (r.settled) this.deps.bus.lifecycle(tid, "agent_settled");
      return r;
    } catch (e: any) {
      account(e?.usage);
      throw e;
    } finally {
      // agent_end 只是生命周期信号，绝不产生 done（ADR-09）
      this.deps.bus.lifecycle(full.taskId ?? "unknown", "agent_end");
    }
  }

  private baseReq(node: DagNode, role: RunRequest["role"], systemPrompt: string, task: string,
                  journal: { session: string; call: string }, tools?: string[]): RunRequest {
    const dir = node.model ? modelDirName(node.model) : undefined;
    return {
      role, systemPrompt, task, cwd: this.deps.ws.dir,
      taskId: node.taskId, phase: node.phase,
      journal: this.journal(journal.session, journal.call),
      ...(tools ? { tools } : {}),
      // R11：并行任务只可写自己的 model 目录，绝不写 master_plan / all_results_summary
      ...(dir ? { writablePrefixes: [`${DIR.programming}/${dir}/`] } : {}),
    };
  }

  private masterPlanPath(): string { return join(this.deps.ws.paths.modeling, "master_plan.md"); }

  /** 评审可以跑代码（ADR-0014），但不能改实现：评审前对本模型目录做字节快照、评审后还原；
   *  共享数据集和 master_plan 按 P1 结束时的快照还原（A2/F3 的字节级保护扩展到评审能触达的全部产物）。 */
  private withReviewGuard<T>(absModelDir: string, taskId: string, fn: () => Promise<T>): Promise<T> {
    mkdirSync(join(this.deps.ws.dir, SCRATCH_DIR), { recursive: true });
    const snap = captureFiles([absModelDir]);
    return fn().finally(() => {
      const { restored, removed } = restoreFiles(snap, this.deps.ws.dir);
      if (restored.length || removed.length)
        this.deps.bus.warn(`Reverted changes made during review: ${[...restored, ...removed].join(", ")}`, 2, taskId);
      this.restorePhase1(taskId);
    });
  }

  async run(signal?: AbortSignal): Promise<RunSummary> {
    const { bus, ws, config } = this.deps;
    const t0 = Date.now();
    bus.status("SolveX: Multi-Model Pipeline Started", 1);
    bus.info(`Workspace: ${ws.dir}`, 1);

    let models: string[];
    let masterPlan = "";
    const preexisting = existsSync(this.masterPlanPath());
    if (preexisting) {
      masterPlan = readFileSync(this.masterPlanPath(), "utf-8");
      models = parseModels(masterPlan);
    } else if (this.deps.skipToWriting) {
      throw new Error("Cannot skip to writing: master_plan.md not found");
    } else {
      // Step A：P1 必须先跑完，才能知道模型数量并构建完整 DAG（静态 DAG 无法预建）。
      const p1: DagNode = { id: "P1", taskId: "P1", label: "Phase 1: Master Plan",
        phase: 1, kind: "stage", dependsOn: [], role: "modeling" };
      this.nodeState(p1, "running");
      try {
        await this.runNode(p1, signal, () => masterPlan, (v) => { masterPlan = v; });
        this.nodeState(p1, "done");
        this.p1Done = true;
      } catch (e) { this.nodeState(p1, "failed"); throw e; }
      bus.barrier("barrier-master-plan", "released", 1, 1);
      models = parseModels(masterPlan);
    }
    this.freezePhase1();
    if (this.deps.modelsOverride?.length) models = this.deps.modelsOverride;
    if (!models.length) models = ["Model 1"];
    this.models = models;

    const dag = buildDag(models);
    // 续跑不在这里做任何跳过：P2 节点照常执行，已完成的 Agent 调用由日志回放（见 journal()）。
    const tasks: SchedTask[] = dag.map((node) => {
      const shouldSkip =
        node.id === "P1" || node.id === "barrier-master-plan"   // Step A 已完成 / 已有计划
        || (this.deps.skipToWriting && node.id !== "P3" && node.id !== "P4");
      return { ...node, skip: shouldSkip,
        run: (sig?: AbortSignal) => this.runNode(node, sig, () => masterPlan,
          (v) => { masterPlan = v; }) };
    });

    const result = await schedule(tasks, {
      concurrency: config.concurrency,
      signal,
      onState: (node, state) => {
        // Step A 已执行的 P1 / 首个屏障不能被后续 skip 覆盖成 skipped
        if (this.p1Done && state === "skipped"
            && (node.id === "P1" || node.id === "barrier-master-plan")) return;
        this.nodeState(node, state);
      },
      onBarrier: (id, st, completedN, total) => bus.barrier(id, st, completedN, total),
    });

    const status = result.aborted ? "aborted" : result.failed.length ? "failed" : "completed";
    const summary: RunSummary = {
      sessionId: ws.id, status,
      models: models.map((m) => this.state.models.find((x) => x.name === m)
        ?? { name: m, dir: modelDirName(m), verdict: "unknown", issues: [] }),
      usageByTask: this.state.usageByTask,
      issues: this.state.issues,
      elapsedMs: Date.now() - t0,
      totalTokens: Object.values(this.state.usageByTask).reduce((a, u) => a + u.input + u.cacheRead + u.output, 0),
      totalCost: Object.values(this.state.usageByTask).reduce((a, u) => a + (u.cost ?? 0), 0),
    };
    bus.status(`SolveX ${status} in ${(summary.elapsedMs / 1000).toFixed(1)}s`, 4);
    bus.complete(summary);
    return summary;
  }

  private async runNode(node: DagNode, signal: AbortSignal | undefined,
                        getPlan: () => string, setPlan: (v: string) => void): Promise<void> {
    const { bus, ws } = this.deps;
    const phase = node.phase;

    if (node.id === "P1") {
      bus.status("Phase 1: Creating Master Plan", 1, node.taskId);
      bus.step("ModelingAgent: Creating multi-model Master Plan...", 1, node.taskId);
      const vars = { input_text: this.problem("P1"), data_info: this.deps.dataInfo ?? "",
        master_plan_path: this.masterPlanPath() };
      await this.call(this.baseReq(node, "modeling", modelingSystem(), renderPlan(vars),
        { session: "P1", call: "plan" }), signal);
      // 计划和共享数据集都要有；缺什么就在同一会话里催，模型看得到自己已经做过的分析。
      const sharedRel = SHARED_DATA_DIR;
      await this.continueUntil(node, "modeling", modelingSystem(), { session: "P1", prefix: "plan" }, () => [
        ...(existsSync(this.masterPlanPath()) ? [] : [`the master plan at ${this.masterPlanPath()}`]),
        ...(existsSync(join(this.sharedDir(), "data_dictionary.md")) ? [] : [`${sharedRel}/data_dictionary.md`]),
        ...(existsSync(this.sharedDir()) && readdirSync(this.sharedDir()).some((f) => /\.(csv|parquet|json)$/i.test(f))
          ? [] : [`the cleaned data table(s) (CSV) in ${sharedRel}/`]),
      ], CONTINUE_NUDGES.P1, signal);
      if (!existsSync(this.masterPlanPath()))
        throw new Error(`MasterPlanError: no master plan after the planning call and ${CONTINUE_NUDGES.P1} continuation requests`);
      if (this.hasSharedData()) bus.done(`Shared dataset ready at ${SHARED_DATA_DIR}/`, 1, node.taskId);
      else bus.warn(`Shared dataset still missing; models will parse the raw data themselves`, 1, node.taskId);
      setPlan(readFileSync(this.masterPlanPath(), "utf-8"));
      const parsed = parseModels(getPlan());
      bus.info(`Master Plan contains ${parsed.length} model(s): ${parsed.join(", ")}`, 1, node.taskId);
      bus.done("Master Plan saved to 01_modeling/master_plan.md", 1, node.taskId);
      return;
    }

    if (node.id.startsWith("P2-IMPL:")) {
      const m = node.model!;
      const dir = modelDirName(m);
      const absModelDir = join(ws.paths.programming, dir);
      const planSection = sectionFor(getPlan(), m);
      bus.step(`[${m}] Implementing...`, 2, node.taskId);
      const problem = this.problem("P2");
      let prompt = renderImplement({ input_text: problem, data_info: this.deps.dataInfo ?? "",
        model_name: m, model_plan_section: planSection, abs_model_dir: absModelDir })
        + (this.hasSharedData() ? sharedDataNote(this.sharedDir()) : "");
      // 该模型的实现会话：摘要补写、自检修订、之后各轮评审修复都发进这同一个会话。
      const session = node.taskId;
      let call = "impl";
      for (let attempt = 0; attempt < 2; attempt++) {
        const r = await this.call(this.baseReq(node, "programming", programmingSystem(), prompt,
          { session, call }), signal);
        bus.done(`${m}: Code saved`, 2, node.taskId);
        const summaryPath = join(absModelDir, "results_summary.md");
        // ADR-0009/0014：交付物（摘要 + 结果契约）不全就在实现会话里催它接着做；
        // 仍缺摘要时才由纯代码扫描目录生成证据型摘要，不再抹掉计算结果。
        await this.continueUntil(node, "programming", programmingSystem(), { session, prefix: call },
          () => ["results_summary.md", "run.py", "results.json"].filter((f) => !existsSync(join(absModelDir, f)))
            .map((f) => `${absModelDir}/${f}`), CONTINUE_NUDGES.IMPL, signal);
        if (!existsSync(summaryPath)) {
          ensureSummary(absModelDir, m);
          bus.warn(`${m}: results_summary.md still missing — generated evidence-based summary from artifacts`, 2, node.taskId);
        }
        const verdict = parseVerdict({ text: r.text, dir: absModelDir });
        if (verdict.status === "satisfied") break;
        if (attempt === 0 && verdict.status === "needs_revision") {
          prompt = renderRevision({ input_text: problem, data_info: this.deps.dataInfo ?? "",
            model_name: m, model_plan_section: planSection,
            prev_summary: readFileSync(summaryPath, "utf-8"), abs_model_dir: absModelDir });
          call = "revision";
        } else break;
      }
      this.restorePhase1(node.taskId);
      await this.reproGate(node, m, absModelDir, "impl", signal);
      const issues = validateModelOutput(absModelDir);
      this.state.issues.push(...issues.map((i) => ({ ...i, model: m })));
      this.state.models.push({ name: m, dir, verdict: parseVerdict({ dir: absModelDir }).status, issues });
      for (const i of [...issues, ...validateSummaryShape(readFileSync(join(absModelDir, "results_summary.md"), "utf-8"))])
        bus.warn(`${m} validation issue: ${i.code}${i.evidence ? ` (${i.evidence})` : ""}`, 2, node.taskId);
      if (!issues.length) bus.done(`${m}: Output validation passed`, 2, node.taskId);
      return;
    }

    if (node.id.startsWith("P2-REVIEW:")) {
      const m = node.model!;
      const dir = modelDirName(m);
      const absModelDir = join(ws.paths.programming, dir);
      const summaryPath = join(absModelDir, "results_summary.md");
      const reviewPath = join(ws.paths.modeling, `${dir}_review.md`);
      // 修复意见发进该模型的实现会话（不另开修复 Agent），taskId / 模型配置 / 写权限都沿用实现节点。
      const implNode: DagNode = { ...node, id: `P2-IMPL:${dir}`, taskId: `P2-IMPL:${dir}`, role: "programming" };
      let verdict = parseVerdict({});
      let round = 0;
      // 评审最多 MAX_REVIEW_ROUNDS 次：每轮从当前状态重新评审（上一轮意见不带入），
      // 通过即止；第 MAX_REVIEW_ROUNDS 轮的修复做完后直接放行，不再评审。
      while (round < MAX_REVIEW_ROUNDS) {
        round++;
        bus.step(`[${m}] Reviewing (round ${round}/${MAX_REVIEW_ROUNDS})...`, 2, node.taskId);
        const reviewPrompt = renderReview({ model_name: m, problem: this.problem("P2"),
          model_plan: sectionFor(getPlan(), m),
          results: existsSync(summaryPath) ? readFileSync(summaryPath, "utf-8") : "",
          review_path: reviewPath });
        // 评审以 submit_review 结束（ADR-0015）：结论和书面评审都是提交参数，check 不合格当场退回。
        // r5：写了 12 KB 却漏结论行；r6：读了 3 个文件就空回复、追问结论后直接 SATISFIED。
        const submit = reviewSubmitTool();
        const session = `${node.taskId}.review-${round}`;
        const reviewCall = (task: string, call: string) => this.withReviewGuard(absModelDir, node.taskId, () =>
          this.call({ ...this.baseReq(node, "review", reviewSystem(), task, { session, call }, ROLE_TOOLS.review), submit }, signal));
        const rr = await reviewCall(reviewPrompt, "review");
        const texts = [rr.text ?? ""];
        const sub = await this.nudgeSubmit(node, REVIEW_TOOL, SUBMIT_NUDGES.REVIEW, rr, async (msg, k) => {
          const r = await reviewCall(msg, `submit-${k}`);
          texts.push(r.text ?? "");
          return r;
        });
        let reviewText: string;
        if (sub) {
          reviewText = formatReview(sub);
          verdict = parseVerdict({ text: reviewText });
        } else {
          // 兜底（r7 验证提交工具后删除）：始终没有被接受的提交，就从回复文字里取最长的评审和结论行。
          bus.warn(`${m}: review round ${round} never got an accepted ${REVIEW_TOOL} — falling back to the reply text`, 2, node.taskId);
          const best = texts.reduce((a, b) => (reviewBody(b).length > reviewBody(a).length ? b : a), "");
          const stated = texts.map((t) => parseVerdict({ text: t })).find((v) => v.status !== "unknown");
          reviewText = stated && parseVerdict({ text: best }).status === "unknown"
            ? `${best}\n\nVERIFICATION_RESULT: ${stated.status.toUpperCase()}\n` : best;
          verdict = parseVerdict({ text: reviewText });
          if (verdict.status === "unknown" && (verdict.issuesFound || verdict.fixInstructions || /Issues Found|Fix Instructions/i.test(reviewText))) {
            bus.warn(`${m}: review round ${round} has no verdict but lists issues — treating as NEEDS_REVISION`, 2, node.taskId);
            verdict = { ...verdict, status: "needs_revision" };
          }
        }
        if (reviewText.trim()) {
          // 内容没变就不重写：下面「修复后摘要是否更新」按 mtime 比较，续跑回放时重写会把旧摘要误判成未更新，
          // 进而在已完成的会话末尾发起一次新的真实调用（r7 续跑实测）。
          writeIfChanged(join(ws.paths.modeling, `${dir}_review_r${round}.md`), reviewText);
          writeIfChanged(reviewPath, reviewText);
        }
        if (verdict.status === "unknown") bus.warn(`${m}: review round ${round} produced no verdict`, 2, node.taskId);
        else bus.info(`${m}: review round ${round} verdict = ${verdict.status}`, 2, node.taskId);
        if (verdict.status !== "needs_revision") break;

        // 标题不规范时 cut 不出段落：退回整份评审作为修复意见。
        const fixSection = verdict.fixInstructions ?? verdict.issuesFound ?? reviewText;
        const fixPrompt = renderReviewFix({ round, max_rounds: MAX_REVIEW_ROUNDS, model_name: m,
          abs_model_dir: absModelDir, fix_section: fixSection });
        const { r: fr, submitted: fixed, changed, baseline } = await this.fixCall(implNode, m, absModelDir, fixPrompt, `fix-${round}`, true, signal);
        if (fr.turnCapped) bus.warn(`${m}: targeted revision round ${round} hit the turn limit`, 2, node.taskId);
        else bus.done(`${m}: Targeted revision applied (round ${round})`, 2, node.taskId);
        this.restorePhase1(implNode.taskId);
        await this.reproGate(implNode, m, absModelDir, `fix-${round}`, signal);
        // 复审读的是 results_summary.md：修复后没更新就在同一会话里补一轮摘要，否则复审看到的是旧结果。
        // 按修复请求时落盘的指纹判断内容有没有变（不看 mtime：续跑回放会重写评审文件、刷新 mtime，
        // r7 续跑实测因此在已完成的会话末尾发起了新的真实调用）。实现方选择不改（已说明理由）时不需要补摘要。
        const declined = !!fixed && !changed.length;
        // 复现修复也可能改摘要，所以在复现门禁之后重新比对。
        const summaryChanged = changedFiles(baseline, fingerprint(absModelDir)).includes("results_summary.md");
        if (!declined && (!existsSync(summaryPath) || !summaryChanged)) {
          bus.warn(`${m}: results_summary.md not updated after revision — requesting a summary turn`, 2, node.taskId);
          await this.call(this.baseReq(implNode, "programming", programmingSystem(),
            renderSummaryRetry({ abs_model_dir: absModelDir }), { session: implNode.taskId, call: `fix-${round}-summary` }), signal);
        }
        if (round === MAX_REVIEW_ROUNDS)
          bus.info(`${m}: released after ${MAX_REVIEW_ROUNDS} review rounds (last revision not re-reviewed)`, 2, node.taskId);
      }
      const rec = this.state.models.find((x) => x.dir === dir);
      if (rec) { rec.verdict = verdict.status; rec.reviewRounds = round; }
      bus.done(`${m}: Review complete`, 2, node.taskId);
      return;
    }

    if (node.id === "P3") {
      bus.status("Phase 3: Aggregating Results", 3, node.taskId);
      const critical = this.state.issues.filter((i) => i.severity === "critical");
      if (this.deps.config.strict && critical.length)
        throw new Error(`StrictGate: ${critical.length} critical issue(s) block P4`);
      const { content } = aggregate(ws, this.models.length ? this.models : parseModels(getPlan()));
      bus.done("Aggregated results saved", 3, node.taskId);
      bus.info(`all_results_summary.md: ${content.length} chars (generated by pure code, not LLM)`, 3, node.taskId);
      return;
    }

    if (node.id === "P4") {
      bus.status("Phase 4: Paper Writing", 4, node.taskId);
      bus.step("WritingAgent: Composing LaTeX paper...", 4, node.taskId);
      const allSummary = join(ws.paths.programming, "all_results_summary.md");
      const paperPath = join(ws.paths.paper, "main.tex");
      const prompt = renderPaper({
        input_text: this.problem("P4"),
        master_plan_content: getPlan(),
        all_results_content: existsSync(allSummary) ? readFileSync(allSummary, "utf-8") : "",
        figure_info: figureInfo(ws, this.models.length ? this.models : parseModels(getPlan())),
        abs_paper_path: paperPath,
      });
      // 论文以 submit_paper 结束（ADR-0015）：check 跑完整性门禁（r6：写完引言和 Model 1 就空回复结束、
      // 摘要停在占位符），题面要求备忘录时备忘录是必填参数（r6：没写备忘录）。
      const paperModels = (this.models.length ? this.models : parseModels(getPlan())).length;
      const submit = paperSubmitTool({ paperPath, modelCount: paperModels, problem: this.deps.problem });
      const send = (t: string, c: string) => this.call({ ...this.baseReq(node, "writing", writingSystem(), t,
        { session: "P4", call: c }), submit }, signal);
      const needsMemo = memoRequired(this.deps.problem);
      const first = await send(prompt + submitInstruction(PAPER_TOOL, "the whole paper is written" +
        (needsMemo ? " (pass the memo the problem asks for as its `memo` argument — do not write it into main.tex)" : "")), "paper");
      const paperMissing = () => existsSync(paperPath)
        ? paperGaps(readFileSync(paperPath, "utf-8"), { modelCount: paperModels }).map((g) => `${paperPath}: ${g}`)
        : [paperPath];
      const sub = await this.nudgeSubmit(node, PAPER_TOOL, SUBMIT_NUDGES.P4, first, (msg, k) => send(msg, `paper-submit-${k}`), paperMissing);
      // 产物门：首轮实测 P4 一行论文没写，旧代码照样发「Paper saved」并报告 completed。
      if (!existsSync(paperPath)) throw new Error("PaperMissing: writing agent finished without 04_paper/main.tex");
      if (!sub) {
        const gaps = paperGaps(readFileSync(paperPath, "utf-8"), { modelCount: paperModels, problem: this.deps.problem });
        bus.warn(`P4: ${PAPER_TOOL} never accepted after ${SUBMIT_NUDGES.P4} nudges` +
          (gaps.length ? ` — missing ${gaps.join("; ")}` : ""), 4, node.taskId);
      }
      bus.done("Paper saved to 04_paper/main.tex", 4, node.taskId);
      return;
    }
  }
}
