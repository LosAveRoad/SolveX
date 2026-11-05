import { ROLE_TOOLS, type AgentRunner, type RunRequest, type RunResult,
         type EventBus } from "@solvex/core";
import { loadRealSdk, type PiSdk, type PiSessionLike } from "./sdk.js";
import { createBridge } from "./eventBridge.js";
import type { ModelRuntimeManager } from "./modelRuntime.js";
import { snapshotFiles, diffFiles } from "./files.js";

export type PiRunnerOptions = {
  bus: EventBus;
  /** 注入点：单测传 FakeSdk，生产留空走真实 SDK（唯一 import 点）。 */
  sdk?: PiSdk;
  modelRuntime?: ModelRuntimeManager;
  agentDir?: string;
  extensionFactories?: any[];
  customTools?: any[];
};

/** 一阶段一 session 的 Pi 适配层（§4.3 六步 / T3.2）。 */
export class PiAgentRunner implements AgentRunner {
  /** 最近一次 createAgentSession 的 options（供单测与 inspect 审计）。 */
  public lastOptions: any = undefined;
  constructor(private readonly opts: PiRunnerOptions) {}

  async run(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    const sdk: PiSdk = this.opts.sdk ?? await loadRealSdk();
    const agentDir = this.opts.agentDir ?? sdk.getAgentDir();

    const loader = new sdk.DefaultResourceLoader({
      cwd: req.cwd,
      agentDir,
      settingsManager: sdk.SettingsManager.create(req.cwd, agentDir),
      systemPromptOverride: () => req.systemPrompt,
      appendSystemPromptOverride: () => [],
      ...(this.opts.extensionFactories?.length
        ? { extensionFactories: this.opts.extensionFactories } : {}),
    });
    await loader.reload();

    const model = req.model ? this.opts.modelRuntime?.resolve(req.model.provider, req.model.id) : undefined;
    const scopedModels = req.scopedModels && this.opts.modelRuntime
      ? this.opts.modelRuntime.scopedModels(req.scopedModels) : undefined;

    const options: any = {
      cwd: req.cwd,
      sessionManager: sdk.SessionManager.inMemory(),
      resourceLoader: loader,
      tools: req.tools ?? ROLE_TOOLS[req.role],
      ...(this.opts.customTools?.length ? { customTools: this.opts.customTools } : {}),
      ...(this.opts.modelRuntime ? { modelRuntime: this.opts.modelRuntime.rt } : {}),
      ...(model ? { model } : {}),
      ...(req.thinkingLevel ? { thinkingLevel: req.thinkingLevel } : {}),
      ...(scopedModels?.length ? { scopedModels } : {}),
    };
    this.lastOptions = options;

    const { session } = await sdk.createAgentSession(options);
    const taskId = req.taskId ?? "unknown";
    const bus = this.opts.bus;
    const bridge = createBridge({ taskId, phase: req.phase }, bus);

    const before = snapshotFiles(req.cwd);
    let turns = 0, settled = false;
    let usage = { input: 0, output: 0, cost: 0 };
    const collect = (u: any) => {
      if (!u) return;
      usage.input += u.input ?? 0;
      usage.output += u.output ?? 0;
      const c = u.cost;
      usage.cost += typeof c === "number" ? c : (c?.total ?? 0);
    };

    const unsubscribe = session.subscribe((event: any) => {
      bridge(event);
      collect(event?.message?.usage ?? event?.assistantMessageEvent?.usage);
      if (event?.type === "turn_end") {
        turns++;
        if (req.maxTurns && turns >= req.maxTurns) void session.abort();
      }
      if (event?.type === "agent_settled") settled = true;
    });

    const onAbort = () => { void session.abort(); };
    if (signal?.aborted) onAbort();   // 取消可能发生在 session 创建之前
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      await session.prompt(req.task);
      if (signal?.aborted) await session.waitForIdle();
      return {
        text: session.getLastAssistantText() ?? "",
        artifacts: diffFiles(req.cwd, before),
        usage,
        settled,
      };
    } finally {
      signal?.removeEventListener("abort", onAbort);
      unsubscribe();     // 抛错路径也保证
      session.dispose(); // 抛错路径也保证
    }
  }
}
