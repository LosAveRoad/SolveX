import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  prepareWorkspace, ingestData, listSessions, scanArtifacts, writeSessionMeta,
  EventBus, SolveXFlow, FakeAgentRunner, DEFAULT_CONFIG,
  type AgentRunner, type ModelConfig, type WorkspaceInfo,
} from "@solvex/core";
import { PiAgentRunner, sharedModelRuntime } from "@solvex/pi-runtime";
import { attachEventLog, readEvents } from "./eventLog.js";
import { stageSnapshot } from "./stages.js";

export type Session = {
  id: string; ws: WorkspaceInfo; bus: EventBus; controller: AbortController;
  status: "running" | "completed" | "failed" | "aborted"; startedAt: number;
};

export class SessionRegistry {
  private readonly sessions = new Map<string, Session>();
  constructor(private readonly opts: { fake?: boolean; sessionRoot: string;
    configPath?: string; modelsPath?: string }) {}

  private async runner(bus: EventBus): Promise<AgentRunner> {
    if (this.opts.fake) return new FakeAgentRunner({ synthetic: true });
    const modelRuntime = await sharedModelRuntime({ modelsPath: this.opts.modelsPath });
    return new PiAgentRunner({ bus, ...(modelRuntime ? { modelRuntime } : {}) });
  }

  async create(params: { text: string; files: { filename: string; buffer: Buffer }[];
                         concurrency?: number; strict?: boolean; byPhase?: any }): Promise<Session> {
    if (!params.text?.trim()) throw new Error("empty problem text");
    const ws = prepareWorkspace({ root: this.opts.sessionRoot, problem: params.text });
    const tmp: string[] = [];
    try {
      for (const f of params.files) {
        const safe = f.filename.replace(/[/\\]/g, "_");
        const p = join(mkdtempSync(join(tmpdir(), "solvex-up-")), safe);
        writeFileSync(p, f.buffer); tmp.push(p);
      }
      if (tmp.length) await ingestData(ws, tmp);
    } finally { for (const p of tmp) try { rmSync(p, { force: true }); } catch { /* noop */ } }

    const bus = new EventBus();
    attachEventLog(ws, bus, false); // 思考正文默认不落盘
    const controller = new AbortController();
    const session: Session = { id: ws.id, ws, bus, controller, status: "running", startedAt: Date.now() };
    this.sessions.set(ws.id, session);

    const { ConfigStore } = await import("@solvex/pi-runtime");
    const config: ModelConfig = {
      ...new ConfigStore(this.opts.configPath).load(),
      ...(params.concurrency ? { concurrency: params.concurrency } : {}),
      ...(params.strict !== undefined ? { strict: params.strict } : {}),
      ...(params.byPhase ? { byPhase: params.byPhase } : {}),
    };
    const flow = new SolveXFlow({ runner: await this.runner(bus), bus, ws, config,
      problem: params.text,
      dataInfo: params.files.length ? `\nDATA FILES: ${params.files.map((f) => f.filename).join(", ")}\n` : "" });

    void flow.run(controller.signal).then((summary) => {
      session.status = summary.status === "completed" ? "completed" : "failed";
      writeSessionMeta(ws, { status: session.status });
    }).catch(() => {
      session.status = "failed"; bus.error("pipeline crashed");
      writeSessionMeta(ws, { status: "failed" });
    });
    return session;
  }

  get(id: string): Session | undefined {
    const s = this.sessions.get(id);
    if (s) return s;
    // 进程重启后从磁盘恢复只读 session（用于回放）
    const p = join(this.opts.sessionRoot, id);
    try {
      const ws = prepareWorkspace({ root: this.opts.sessionRoot, sessionId: id, mode: "resume" });
      const s: Session = { id, ws, bus: new EventBus(), controller: new AbortController(),
        status: "completed", startedAt: 0 };
      this.sessions.set(id, s); return s;
    } catch { return undefined; }
  }
  list() { return listSessions(this.opts.sessionRoot); }
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
}
