import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { AgentRunner, RunRequest, RunResult } from "../ports/AgentRunner.js";
import { DEFAULT_MAX_TURNS } from "../ports/AgentRunner.js";
import type { EventBus } from "../events/EventBus.js";
import type { Issue, Phase, RunSummary, StageNode, ThinkingLevel } from "../events/types.js";
import type { ModelConfig, PhaseKey } from "../config/schema.js";
import type { WorkspaceInfo } from "../workspace/index.js";
import { DIR, modelDirName } from "../workspace/paths.js";
import { parseModels, sectionFor } from "../contracts/masterPlan.js";
import { parseVerdict } from "../gates/parseVerdict.js";
import { validateModelOutput } from "../gates/validateModelOutput.js";
import { validateSummaryShape } from "../contracts/modelResult.js";
import { ensureSummary } from "../gates/ensureSummary.js";
import {
  modelingSystem, programmingSystem, writingSystem, renderReview,
  renderPlan, renderPlanRetry, renderImplement, renderSummaryRetry,
  renderRevision, renderFix, renderPaper,
  ROLE_TOOLS,
} from "../prompts/index.js";
import { buildDag, type DagNode } from "./dag.js";
import { schedule, type SchedTask } from "./scheduler.js";
import { aggregate, figureInfo } from "./stages.js";
import { completedModels, detectResumeModel } from "./resume.js";
import { initialState, upsertNode, type FlowState } from "./state.js";

export type SolveXFlowDeps = {
  runner: AgentRunner;
  bus: EventBus;
  ws: WorkspaceInfo;
  config: ModelConfig;
  problem: string;
  dataInfo?: string;
  resumeFrom?: number;
  skipToWriting?: boolean;
  modelsOverride?: string[];
};

const PHASE_KEY: Partial<Record<string, PhaseKey>> = {
  P1: "P1", P3: "P3", P4: "P4",
};

/** 四阶段状态机（§5.2）。构造函数只接受 core 抽象，不 import 任何 Pi 符号。 */
export class SolveXFlow {
  private readonly state: FlowState = initialState();
  private p1Done = false;
  constructor(private readonly deps: SolveXFlowDeps) {}

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
    try {
      const r = await this.deps.runner.run(full, signal);
      this.state.usageByTask[full.taskId ?? "unknown"] = {
        input: r.usage.input, output: r.usage.output, cost: r.usage.cost ?? 0 };
      if (r.settled) this.deps.bus.lifecycle(full.taskId ?? "unknown", "agent_settled");
      return r;
    } finally {
      // agent_end 只是生命周期信号，绝不产生 done（ADR-09）
      this.deps.bus.lifecycle(full.taskId ?? "unknown", "agent_end");
    }
  }

  private baseReq(node: DagNode, role: RunRequest["role"], systemPrompt: string, task: string,
                  tools?: string[]): RunRequest {
    const dir = node.model ? modelDirName(node.model) : undefined;
    return {
      role, systemPrompt, task, cwd: this.deps.ws.dir,
      taskId: node.taskId, phase: node.phase,
      ...(tools ? { tools } : {}),
      // R11：并行任务只可写自己的 model 目录，绝不写 master_plan / all_results_summary
      ...(dir ? { writablePrefixes: [`${DIR.programming}/${dir}/`] } : {}),
    };
  }

  private masterPlanPath(): string { return join(this.deps.ws.paths.modeling, "master_plan.md"); }

  /** 保护 Master Plan（评审只读工具 + 字节级快照，双保险消除 A2/F3）。 */
  private withMasterPlanGuard<T>(fn: () => Promise<T>): Promise<T> {
    const p = this.masterPlanPath();
    const before = existsSync(p) ? readFileSync(p) : null;
    return fn().finally(() => {
      if (before && (!existsSync(p) || !readFileSync(p).equals(before))) {
        writeFileSync(p, before);
        this.deps.bus.warn("Restored master_plan.md after review (was modified)", 2);
      }
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
    if (this.deps.modelsOverride?.length) models = this.deps.modelsOverride;
    if (!models.length) models = ["Model 1"];

    const dag = buildDag(models);
    const completed = completedModels(ws, models);
    const resumeFrom = this.deps.resumeFrom ?? (preexisting ? detectResumeModel(ws, models) : 0);

    const tasks: SchedTask[] = dag.map((node) => {
      const modelName = node.model ?? "";
      const shouldSkip =
        node.id === "P1" || node.id === "barrier-master-plan"   // Step A 已完成 / resume 已有计划
        || (this.deps.skipToWriting && node.id !== "P3" && node.id !== "P4")
        || (resumeFrom > 0 && (node.id.startsWith("P2-IMPL:") || node.id.startsWith("P2-REVIEW:"))
            && completed.has(modelName));
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
      models: this.state.models.length ? this.state.models : models.map((m) => ({
        name: m, dir: modelDirName(m), verdict: "unknown", issues: [] })),
      usageByTask: this.state.usageByTask,
      issues: this.state.issues,
      elapsedMs: Date.now() - t0,
      totalTokens: Object.values(this.state.usageByTask).reduce((a, u) => a + u.input + u.output, 0),
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
      const vars = { input_text: this.deps.problem, data_info: this.deps.dataInfo ?? "",
        master_plan_path: this.masterPlanPath() };
      await this.call(this.baseReq(node, "modeling", modelingSystem(), renderPlan(vars)), signal);
      if (!existsSync(this.masterPlanPath())) {
        bus.warn("Master Plan not saved, retrying...", 1, node.taskId);
        await this.call(this.baseReq(node, "modeling", modelingSystem(), renderPlanRetry(vars)), signal);
      }
      if (!existsSync(this.masterPlanPath())) throw new Error("MasterPlanError: modeling agent failed after 2 attempts");
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
      let prompt = renderImplement({ input_text: this.deps.problem, data_info: this.deps.dataInfo ?? "",
        model_name: m, model_plan_section: planSection, abs_model_dir: absModelDir });
      for (let attempt = 0; attempt < 2; attempt++) {
        const r = await this.call(this.baseReq(node, "programming", programmingSystem(), prompt), signal);
        bus.done(`${m}: Code saved`, 2, node.taskId);
        const summaryPath = join(absModelDir, "results_summary.md");
        if (!existsSync(summaryPath)) {
          // ADR-0009：先给一次专门的短会话让模型自己写摘要（P1 的 renderPlanRetry 同款兜底），
          // 仍缺失时才由纯代码扫描目录生成含真实 CSV 数值的证据型摘要，不再抹掉计算结果。
          bus.warn(`${m}: results_summary.md missing — requesting a dedicated summary turn`, 2, node.taskId);
          await this.call(this.baseReq(node, "programming", programmingSystem(),
            renderSummaryRetry({ abs_model_dir: absModelDir })), signal);
        }
        if (!existsSync(summaryPath)) {
          ensureSummary(absModelDir, m);
          bus.warn(`${m}: results_summary.md still missing — generated evidence-based summary from artifacts`, 2, node.taskId);
        }
        const verdict = parseVerdict({ text: r.text, dir: absModelDir });
        if (verdict.status === "satisfied") break;
        if (attempt === 0 && verdict.status === "needs_revision") {
          prompt = renderRevision({ input_text: this.deps.problem, data_info: this.deps.dataInfo ?? "",
            model_name: m, model_plan_section: planSection,
            prev_summary: readFileSync(summaryPath, "utf-8"), abs_model_dir: absModelDir });
        } else break;
      }
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
      bus.step(`[${m}] Reviewing...`, 2, node.taskId);
      const reviewPrompt = renderReview({ model_name: m, problem: this.deps.problem,
        model_plan: sectionFor(getPlan(), m),
        results: existsSync(summaryPath) ? readFileSync(summaryPath, "utf-8") : "",
        review_path: reviewPath });
      await this.withMasterPlanGuard(() =>
        this.call(this.baseReq(node, "review", reviewPrompt, reviewPrompt, ROLE_TOOLS.review), signal));
      const verdict = parseVerdict({ dir: absModelDir, reviewPath });
      if (verdict.warn) bus.warn(verdict.warn, 2, node.taskId);
      if (verdict.status === "needs_revision") {
        const fixSection = verdict.fixInstructions ?? verdict.issuesFound ?? "";
        const fixPrompt = renderFix({ input_text: this.deps.problem, data_info: this.deps.dataInfo ?? "",
          model_name: m, abs_model_dir: absModelDir, fix_section: fixSection });
        await this.call(this.baseReq(node, "programming", programmingSystem(), fixPrompt), signal);
        bus.done(`${m}: Targeted revision applied`, 2, node.taskId);
      }
      const rec = this.state.models.find((x) => x.dir === dir);
      if (rec) rec.verdict = verdict.status;
      bus.done(`${m}: Review complete`, 2, node.taskId);
      return;
    }

    if (node.id === "P3") {
      bus.status("Phase 3: Aggregating Results", 3, node.taskId);
      const critical = this.state.issues.filter((i) => i.severity === "critical");
      if (this.deps.config.strict && critical.length)
        throw new Error(`StrictGate: ${critical.length} critical issue(s) block P4`);
      const { content } = aggregate(ws, this.state.models.length ? this.state.models.map((x) => x.name)
        : parseModels(getPlan()));
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
        input_text: this.deps.problem,
        master_plan_content: getPlan(),
        all_results_content: existsSync(allSummary) ? readFileSync(allSummary, "utf-8") : "",
        figure_info: figureInfo(ws, this.state.models.length ? this.state.models.map((x) => x.name)
          : parseModels(getPlan())),
        abs_paper_path: paperPath,
      });
      await this.call(this.baseReq(node, "writing", writingSystem(), prompt), signal);
      bus.done("Paper saved to 04_paper/main.tex", 4, node.taskId);
      return;
    }
  }
}
