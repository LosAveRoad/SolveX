import { randomUUID } from "node:crypto";
import { writeFileSync, mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import {
  prepareWorkspace, ingestData, listAllRuns, findRun, runsRoot, scanArtifacts,
  writeSessionMeta, writeRuntime, readRuntime, buildRuntimeConfig, toModelConfig,
  sanitizeOverrides, runtimeSummary, META_FILE, EventBus, SolveXFlow,
  type AgentRunner, type ModelConfig, type WorkspaceInfo,
  type RuntimeSnapshot, type RuntimeConfig, type RuntimeOverrides,
} from "@solvex/core";
import { PiAgentRunner, sharedModelRuntime } from "@solvex/pi-runtime";
import { attachEventLog, readEvents } from "./eventLog.js";
import { stageSnapshot } from "./stages.js";

export type Session = {
  id: string; ws: WorkspaceInfo; bus: EventBus; controller: AbortController;
  status: "running" | "completed" | "failed" | "aborted"; startedAt: number;
  workspaceId?: string; runtime?: RuntimeSnapshot;
  /** 本进程里该 run 的流水线结束（含 abort 后在跑任务收尾）。续跑前必须等它，避免两条流水线同写一个目录。 */
  finished?: Promise<void>;
};

export type CreateParams = {
  text: string;
  files: { filename: string; buffer: Buffer }[];
  concurrency?: number;
  strict?: boolean;
  byPhase?: unknown;
  workspaceId?: string;
  problemFilename?: string;
  /** 启动参数覆盖；只接受白名单字段，写入该 run 的 runtime.json。 */
  runtimeOverrides?: unknown;
};

export class SessionRegistry {
  private readonly sessions = new Map<string, Session>();
  constructor(private readonly opts: { sessionRoot: string; workspaceRoot?: string;
    configPath?: string; modelsPath?: string; mcpConfigPath?: string }) {}

  /** 生产路径只构造真实 runner。测试通过 spy 本方法注入 FakeAgentRunner（无公开开关）。 */
  private async runner(bus: EventBus): Promise<AgentRunner> {
    const modelRuntime = await sharedModelRuntime({ modelsPath: this.opts.modelsPath });
    return new PiAgentRunner({ bus, ...(modelRuntime ? { modelRuntime } : {}),
      ...(this.opts.mcpConfigPath ? { mcpConfigPath: this.opts.mcpConfigPath } : {}) });
  }

  private indexOpts() {
    return { workspaceRoot: this.opts.workspaceRoot, sessionRoot: this.opts.sessionRoot };
  }

  private overridesFor(params: CreateParams): RuntimeOverrides {
    const raw = params.runtimeOverrides && typeof params.runtimeOverrides === "object"
      ? params.runtimeOverrides as Record<string, unknown> : {};
    return sanitizeOverrides({
      ...raw,
      ...(params.concurrency !== undefined ? { concurrency: params.concurrency } : {}),
      ...(params.strict !== undefined ? { strict: params.strict } : {}),
      ...(params.byPhase !== undefined ? { byPhase: params.byPhase } : {}),
    });
  }

  private async effectiveConfig(overrides: RuntimeOverrides): Promise<{ base: ModelConfig; runtime: RuntimeConfig }> {
    const { ConfigStore } = await import("@solvex/pi-runtime");
    const base: ModelConfig = new ConfigStore(this.opts.configPath).load();
    return { base, runtime: buildRuntimeConfig(base, overrides) };
  }

  /**
   * 一道题一个工作区，每次运行一个独立 run 目录：
   * workspaces/{workspaceId}/runs/{runId}/（旧版 /api/run 仍写平铺 sessions/）。
   * runId 用 UUID，保证同一工作区并行启动时也不会撞目录。
   */
  async create(params: CreateParams): Promise<Session> {
    if (!params.text?.trim()) throw new Error("empty problem text");
    const root = params.workspaceId && this.opts.workspaceRoot
      ? runsRoot(this.opts.workspaceRoot, params.workspaceId)
      : this.opts.sessionRoot;
    const runId = randomUUID();
    const ws = prepareWorkspace({ root, sessionId: runId, problem: params.text });
    if (params.workspaceId) writeSessionMeta(ws, { workspaceId: params.workspaceId });
    const tmp: string[] = [];
    try {
      for (const f of params.files) {
        const safe = f.filename.replace(/[/\\]/g, "_");
        const p = join(mkdtempSync(join(tmpdir(), "solvex-up-")), safe);
        writeFileSync(p, f.buffer); tmp.push(p);
      }
      if (tmp.length) await ingestData(ws, tmp);
    } finally { for (const p of tmp) try { rmSync(join(p, ".."), { recursive: true, force: true }); } catch { /* noop */ } }

    const overrides = this.overridesFor(params);
    const { base, runtime } = await this.effectiveConfig(overrides);
    const snapshot: RuntimeSnapshot = {
      id: runId,
      ...(params.workspaceId ? { workspaceId: params.workspaceId } : {}),
      createdAt: new Date().toISOString(),
      config: runtime,
      overrides,
      inputs: { ...(params.problemFilename ? { problemFilename: params.problemFilename } : {}),
        files: params.files.map((f) => f.filename) },
    };
    writeRuntime(ws, snapshot);
    const config = toModelConfig(base, runtime);

    const dataInfo = params.files.length ? `\nDATA FILES: ${params.files.map((f) => f.filename).join(", ")}\n` : "";
    writeSessionMeta(ws, { dataInfo });
    return this.launch({ id: runId, ws, config, problem: params.text, dataInfo,
      ...(params.workspaceId ? { workspaceId: params.workspaceId } : {}), runtime: snapshot });
  }

  /**
   * 断点续跑：在同一个 run 目录上重新执行整条流水线。每次 Agent 调用都有自己的会话日志
   * （.solvex/journal/*.jsonl）：已完成的直接回放、不调用模型，中断的从日志接着跑。
   * 配置、题面、数据说明都取自该 run 首次启动时落盘的快照，与中断前保持一致。
   */
  async resume(id: string): Promise<Session> {
    const prev = this.get(id);
    if (!prev) throw new Error("session not found");
    if (prev.status === "running") throw new Error("session is still running");
    await prev.finished;   // abort 只是发出取消信号，在跑的 Agent 收尾后才算真正停下
    const meta = JSON.parse(readFileSync(join(prev.ws.dir, META_FILE), "utf8"));
    const runtime = prev.runtime ?? readRuntime(prev.ws);
    const { base } = await this.effectiveConfig({});
    const config = runtime ? toModelConfig(base, runtime.config) : base;
    const problemFile = join(prev.ws.paths.problem, "problem.md");
    const problem = meta.problem || (existsSync(problemFile) ? readFileSync(problemFile, "utf8") : "");
    if (!problem.trim()) throw new Error("session has no problem text");
    writeSessionMeta(prev.ws, { status: "running" });
    return this.launch({ id, ws: prev.ws, config, problem, dataInfo: meta.dataInfo ?? "",
      ...(prev.workspaceId ? { workspaceId: prev.workspaceId } : {}),
      ...(runtime ? { runtime } : {}) });
  }

  private async launch(o: { id: string; ws: WorkspaceInfo; config: ModelConfig; problem: string;
    dataInfo: string; workspaceId?: string; runtime?: RuntimeSnapshot }): Promise<Session> {
    const { ws, config } = o;
    const bus = new EventBus();
    attachEventLog(ws, bus, config.persistThinking);
    const controller = new AbortController();
    const session: Session = { id: o.id, ws, bus, controller, status: "running",
      startedAt: Date.now(), ...(o.workspaceId ? { workspaceId: o.workspaceId } : {}),
      ...(o.runtime ? { runtime: o.runtime } : {}) };
    this.sessions.set(o.id, session);

    const flow = new SolveXFlow({ runner: await this.runner(bus), bus, ws, config,
      problem: o.problem, dataInfo: o.dataInfo });

    session.finished = flow.run(controller.signal).then((summary) => {
      session.status = session.controller.signal.aborted ? "aborted" : summary.status === "completed" ? "completed" : "failed";
      writeSessionMeta(ws, { status: session.status });
    }).catch(() => {
      session.status = session.controller.signal.aborted ? "aborted" : "failed";
      if (session.status === "failed") bus.error("pipeline crashed");
      writeSessionMeta(ws, { status: session.status });
    });
    return session;
  }

  get(id: string): Session | undefined {
    if (!/^[A-Za-z0-9_-]+$/.test(id)) return undefined;
    const s = this.sessions.get(id);
    if (s) return s;
    // 进程重启后从磁盘恢复只读 session（新嵌套布局 + 旧平铺 sessions 都支持）
    const found = findRun(id, this.indexOpts());
    if (!found) return undefined;
    try {
      const ws = prepareWorkspace({ root: found.root, sessionId: id, mode: "resume" });
      const meta = JSON.parse(readFileSync(join(ws.dir, META_FILE), "utf8"));
      const status: Session["status"] = meta.status === "running" ? "failed" :
        ["completed", "failed", "aborted"].includes(meta.status) ? meta.status : "failed";
      if (status !== meta.status) writeSessionMeta(ws, { status });
      const restored: Session = { id, ws, bus: new EventBus(), controller: new AbortController(),
        status, startedAt: Date.parse(meta.created_at) || 0,
        workspaceId: meta.workspaceId ?? found.workspaceId, runtime: readRuntime(ws) };
      this.sessions.set(id, restored); return restored;
    } catch { return undefined; }
  }
  isRunning(id: string): boolean { return this.sessions.get(id)?.status === "running"; }

  /** 全部 run（新布局 + 旧 sessions），按创建时间倒序。 */
  list() {
    return listAllRuns(this.indexOpts()).map((rec) => {
      const s = this.get(rec.meta.id);
      return { ...rec.meta, workspaceId: rec.workspaceId,
        status: s?.status ?? rec.meta.status,
        runtime: runtimeSummary(s?.runtime) };
    });
  }
  /** 某个题目工作区下的全部 run（含旧版按 workspaceId 关联的历史 run）。 */
  listRuns(workspaceId: string) { return this.list().filter((r) => r.workspaceId === workspaceId); }
  runDetail(id: string) {
    const s = this.get(id);
    if (!s) return undefined;
    const meta = JSON.parse(readFileSync(join(s.ws.dir, META_FILE), "utf8"));
    return { ...meta, id, status: s.status, workspaceId: s.workspaceId,
      runtime: s.runtime, runtimeSummary: runtimeSummary(s.runtime) };
  }
  owner(id: string): string | undefined { return this.get(id)?.workspaceId; }
  runtime(id: string): RuntimeSnapshot | undefined { return this.get(id)?.runtime; }

  artifacts(id: string) { const s = this.get(id); return s ? scanArtifacts(s.ws) : []; }
  events(id: string, since = 0) {
    const s = this.get(id); if (!s) return [];
    const fromLog = readEvents(s.ws, since);
    return fromLog.length ? fromLog : s.bus.history(since);
  }
  stages(id: string) { const s = this.get(id); return s ? stageSnapshot(s.bus) : []; }
  abort(id: string): boolean {
    const s = this.get(id); if (!s) return false;
    s.controller.abort(); s.status = "aborted";
    s.bus.emit({ type: "lifecycle", taskId: "run", state: "aborted", ts: Date.now() });
    writeSessionMeta(s.ws, { status: "aborted" });
    return true;
  }

  /**
   * 删除运行记录：新布局 workspaces/{id}/runs/ 与旧平铺 sessions/ 都支持。
   * 运行中的任务拒绝删除；目录必须落在托管根内，避免路径逃逸。
   */
  remove(id: string): string {
    const rec = this.list().find((r) => r.id === id);
    if (!rec) throw new Error("运行不存在");
    if (rec.status === "running") throw new Error("运行尚未结束，请先停止后再删除");
    const found = findRun(id, this.indexOpts());
    const dir = this.sessions.get(id)?.ws.dir ?? found?.dir;
    if (!dir) throw new Error("运行目录不存在");
    const abs = resolve(dir);
    const roots = [this.opts.sessionRoot, this.opts.workspaceRoot]
      .filter((r): r is string => Boolean(r)).map((r) => resolve(r));
    if (!roots.some((r) => abs === r || abs.startsWith(r + sep)))
      throw new Error("非法运行目录");
    rmSync(abs, { recursive: true, force: true });
    this.sessions.delete(id);
    return abs;
  }

  /** 删除工作区前清掉它的内存 session；仍有运行中的任务时返回 false。 */
  forgetWorkspace(workspaceId: string): boolean {
    if (this.listRuns(workspaceId).some((r) => r.status === "running")) return false;
    for (const [id, s] of this.sessions) if (s.workspaceId === workspaceId) this.sessions.delete(id);
    return true;
  }
}
