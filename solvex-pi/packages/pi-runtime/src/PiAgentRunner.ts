import { ROLE_TOOLS, injectToolList, toolDescriptorsFor,
         type AgentRunner, type RunRequest, type RunResult, type EventBus } from "@solvex/core";
import { buildCustomTools, safetyExtension } from "../extensions/solvex-tools.js";
import { loadRealSdk, type PiSdk, type PiSessionLike } from "./sdk.js";
import { createBridge } from "./eventBridge.js";
import { discoverToolCatalog } from "./toolDiscovery.js";
import { getSharedMcpManager, type McpManager } from "./mcp.js";
import type { ModelRuntimeManager } from "./modelRuntime.js";
import { snapshotFiles, diffFiles } from "./files.js";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { inspectJournal, addUsage, resumeMessage, lastContextTokens, CALL_ENTRY, RESULT_ENTRY, SUBMIT_DETAILS_KEY,
         type JournalState } from "./journal.js";
import type { SubmitTool } from "@solvex/core";

export type PiRunnerOptions = {
  bus: EventBus;
  /** 注入点：单测传 FakeSdk，生产留空走真实 SDK（唯一 import 点）。 */
  sdk?: PiSdk;
  modelRuntime?: ModelRuntimeManager;
  agentDir?: string;
  extensionFactories?: any[];
  customTools?: any[];
  /** MCP 配置文件路径；不传则用 ~/.solvex/mcp.json（文件不存在即未启用）。 */
  mcpConfigPath?: string;
  /** 测试注入点：传入已连接好的 MCP 管理器，避免起真实进程。 */
  mcpManager?: McpManager;
  /** 上下文超过这个 token 数就触发 Pi compaction；不传沿用 Pi 默认（窗口 − 16K）。 */
  compactAtTokens?: number;
  /** 会话上下文超过这个 token 数时把 xhigh 思考降到 high（默认 THINKING_DOWNGRADE_AT）。 */
  downgradeThinkingAt?: number;
};

export const AGENT_RETRY_POLICY = {
  enabled: true, maxRetries: 6, baseDelayMs: 2000, maxAgentDelayMs: 60000,
} as const;

/** 模型调用在 SDK 重试耗尽后仍失败。携带已消耗的用量，失败调用也计入成本。 */
export class AgentRunError extends Error {
  constructor(public readonly taskId: string, detail: string,
              public readonly usage?: { input: number; output: number; cacheRead: number; cost: number }) {
    super(`AgentRunError[${taskId}]: ${detail}`);
    this.name = "AgentRunError";
  }
}

/**
 * 长上下文下的思考等级。上下文探针（bench/probe，docs/benchmark.md）重放 r6 Model 3 的真实实现会话：
 * 30K–126K 下 max / high 共 30/30 正常调用工具；177K 下 high 9/9 正常、max 只有 5/9——3 次说完
 * "我来修全部 7 个问题"就结束（与 r6 的失败一致），1 次路径写错。退化来自「长上下文 × 最高思考档」的叠加，
 * 不是上下文本身（大海捞针 583K 仍 5/5）。所以会话上下文超过 THINKING_DOWNGRADE_AT 时把 xhigh 降到 high。
 */
export const THINKING_DOWNGRADE_AT = 150_000;
export const downgradeThinking = (level: string | undefined, contextTokens: number,
                                  at: number = THINKING_DOWNGRADE_AT): string | undefined =>
  level === "xhigh" && contextTokens > at ? "high" : undefined;

/**
 * 可选的提前压缩：上下文超过 at 就触发 Pi compaction（保留最近 40K 原文）。默认不启用，沿用 Pi 的
 * 「窗口 − 16K」——探针显示上下文长度本身不是退化原因，提前压缩只会丢信息。
 */
export const COMPACT_KEEP_RECENT_TOKENS = 40_000;
export function compactionPolicy(contextWindow: number | undefined, at: number | undefined):
    { enabled: true; reserveTokens: number; keepRecentTokens: number } | undefined {
  if (!at || !Number.isFinite(at) || !contextWindow || contextWindow <= at + COMPACT_KEEP_RECENT_TOKENS) return undefined;
  return { enabled: true, reserveTokens: contextWindow - at, keepRecentTokens: COMPACT_KEEP_RECENT_TOKENS };
}

export const TURN_BUDGET_WARN = 3;
export const turnBudgetMessage = (left: number): string =>
  `[SolveX turn budget] Only ${left} turns remain in this session. Stop exploring and debugging now. ` +
  `Use the remaining turns to save the deliverables the task requires (for example results_summary.md ` +
  `with the key numbers you already have, or the final paper file), then end your turn.`;

/**
 * 把 core 的提交工具（ADR-0015）包装成 Pi customTool。check 拒绝 → isError，原因原样回给模型；
 * 接受 → 记录参数，details 里带标记写进日志（回放、续跑从日志恢复）。
 */
export function submitCustomTool(sub: SubmitTool, onAccept: (args: Record<string, unknown>) => void): any {
  return {
    name: sub.name, label: sub.name, description: sub.description, parameters: sub.parameters,
    async execute(_id: string, params: any) {
      const args: Record<string, unknown> = params && typeof params === "object" ? params : {};
      let reason: string | null;
      try { reason = await sub.check(args); }
      catch (e) { reason = `SolveX could not check the submission: ${String(e instanceof Error ? e.message : e)}`; }
      if (reason !== null)
        return { content: [{ type: "text", text: `[SolveX] Submission rejected:\n${reason}\nFix this, then call ${sub.name} again.` }],
                 details: { [SUBMIT_DETAILS_KEY]: { accepted: false } }, isError: true };
      onAccept(args);
      return { content: [{ type: "text", text: "[SolveX] Submission accepted. The task is finished — end your turn now " +
                 "with a one-line confirmation; do not call more tools." }],
               details: { [SUBMIT_DETAILS_KEY]: { accepted: true, args } } };
    },
  };
}

/** 一阶段一 session 的 Pi 适配层（§4.3 六步 / T3.2）。 */
export class PiAgentRunner implements AgentRunner {
  /** 最近一次 createAgentSession 的 options（供单测与 inspect 审计）。 */
  public lastOptions: any = undefined;
  constructor(private readonly opts: PiRunnerOptions) {}

  async run(req: RunRequest, signal?: AbortSignal): Promise<RunResult> {
    const sdk: PiSdk = this.opts.sdk ?? await loadRealSdk();
    const agentDir = this.opts.agentDir ?? sdk.getAgentDir();
    const taskId = req.taskId ?? "unknown";

    // 断点续跑：会话日志就是 Pi 自己的 JSONL，一个会话里可以有多次调用（journal.call 区分）。
    // 这次调用已完成 → 回放；中断 → 从日志接着跑；没开始过 → 在同一会话末尾发新任务
    // （例如评审修复意见直接发进该模型的实现会话）。对所有角色一视同仁。
    let journal: JournalState | undefined;
    const call = req.journal?.call ?? "main";
    if (req.journal) {
      const { path } = req.journal;
      mkdirSync(dirname(path), { recursive: true });
      journal = inspectJournal(path, call);
      if (journal.done) {
        return { text: journal.done.text, artifacts: [], usage: { ...journal.usage }, settled: true,
          replayed: true, ...(journal.done.turnCapped ? { turnCapped: true } : {}),
          ...(journal.submitted ? { submitted: journal.submitted } : {}) };
      }
      if (req.maxTurns && journal.turns >= req.maxTurns) {
        // 撞上限后、写完成标记前进程退出：直接补记为截断结束，不再调用模型。
        (sdk.SessionManager.open(path, dirname(path), req.cwd) as any)
          ?.appendCustomEntry?.(RESULT_ENTRY, { call, text: journal.lastText ?? "", turnCapped: true });
        return { text: journal.lastText ?? "", artifacts: [], usage: { ...journal.usage }, settled: true,
          resumed: true, turnCapped: true, ...(journal.submitted ? { submitted: journal.submitted } : {}) };
      }
    }

    // ADR-0011 / ADR-0012：工具清单由运行时发现，且必须与本次 session 实际注册的
    // tools + customTools 同源。MCP 工具先真实连接做 tools/list，再一起进入这三处。
    const mcp = this.opts.mcpManager ?? getSharedMcpManager({ cwd: req.cwd,
      configPath: this.opts.mcpConfigPath });
    await mcp.ready();
    const mcpDescriptors = mcp.descriptors();
    const catalog = [...(await discoverToolCatalog()), ...mcpDescriptors];
    const known = new Set(catalog.map((t) => t.name));
    const requestedTools = req.tools ?? ROLE_TOOLS[req.role];
    const baseTools = requestedTools.filter((t) => known.has(t));
    const mcpTools = mcpDescriptors.filter((d) => !d.roles || d.roles.includes(req.role))
      .map((d) => d.name);
    // 提交工具（ADR-0015）只属于这一次调用：和 MCP 工具一样同时进 tools、customTools 与提示词里的工具清单。
    let submitted: Record<string, unknown> | undefined = journal?.submitted;
    const submitTools = req.submit ? [submitCustomTool(req.submit, (a) => { submitted = a; })] : [];
    if (req.submit) catalog.push({ name: req.submit.name, description: req.submit.description.split("\n")[0].slice(0, 240) });
    const tools = [...new Set([...baseTools, ...mcpTools, ...(req.submit ? [req.submit.name] : [])])];
    const customTools = [...(this.opts.customTools ?? buildCustomTools()), ...mcp.customTools(req.role), ...submitTools];
    const systemPrompt = injectToolList(req.systemPrompt, toolDescriptorsFor(tools, catalog));

    // R11：安全拦截必须挂进每个真实 session（此前只在单测里调用过，生产路径从未生效）。
    const extensionFactories = [
      (pi: any) => safetyExtension(pi, req.writablePrefixes, req.cwd),
      ...(this.opts.extensionFactories ?? []),
    ];
    // 重试预算：Pi 默认 3 次（2s/4s/8s，累计约 14s），首轮实测遇到约 50s 的上游 TLS 中断，
    // 9 个并行会话的 27 次重试全部落在窗口内耗尽。6 次指数退避累计约 2 分钟，覆盖该窗口。
    const model = req.model ? this.opts.modelRuntime?.resolve(req.model.provider, req.model.id) : undefined;
    const settingsManager: any = sdk.SettingsManager.create(req.cwd, agentDir);
    const compaction = compactionPolicy((model as any)?.contextWindow, this.opts.compactAtTokens);
    settingsManager?.applyOverrides?.({ retry: { ...AGENT_RETRY_POLICY }, ...(compaction ? { compaction } : {}) });
    const loader = new sdk.DefaultResourceLoader({
      cwd: req.cwd,
      agentDir,
      settingsManager,
      systemPromptOverride: () => systemPrompt,
      appendSystemPromptOverride: () => [],
      extensionFactories,
    });
    await loader.reload();

    const scopedModels = req.scopedModels && this.opts.modelRuntime
      ? this.opts.modelRuntime.scopedModels(req.scopedModels) : undefined;

    // 工具契约（ADR-0008 / ADR-0011）：发现结果之外的名字一律不进 session，
    // 避免 SDK 静默丢弃后模型用 bash 兜底；自定义工具一定注入 session。
    // 发进已有长会话的新调用（如评审修复发进 175K 的实现会话）一开始就降档。
    const downgradeAt = this.opts.downgradeThinkingAt ?? THINKING_DOWNGRADE_AT;
    const startContext = req.journal ? lastContextTokens(req.journal.path) : 0;
    const startDowngrade = downgradeThinking(req.thinkingLevel, startContext, downgradeAt);
    const thinkingLevel = startDowngrade ?? req.thinkingLevel;
    const sessionManager: any = req.journal
      ? sdk.SessionManager.open(req.journal.path, dirname(req.journal.path), req.cwd)
      : sdk.SessionManager.inMemory();
    const options: any = {
      cwd: req.cwd,
      sessionManager,
      settingsManager,
      resourceLoader: loader,
      tools,
      ...(customTools.length ? { customTools } : {}),
      ...(this.opts.modelRuntime ? { modelRuntime: this.opts.modelRuntime.rt } : {}),
      ...(model ? { model } : {}),
      ...(thinkingLevel ? { thinkingLevel } : {}),
      ...(scopedModels?.length ? { scopedModels } : {}),
    };
    this.lastOptions = options;

    const { session } = await sdk.createAgentSession(options);
    const bus = this.opts.bus;
    const bridge = createBridge({ taskId, phase: req.phase }, bus);

    const before = snapshotFiles(req.cwd);
    // 续跑时轮次与用量从日志里已有的部分接着算，轮次预算不会因为重启而重置。
    let turns = journal?.turns ?? 0, settled = false;
    let lastStop: string | undefined, lastError: string | undefined;
    let turnCapped = false;
    let downgraded = !!startDowngrade || thinkingLevel !== "xhigh";
    const resuming = !!journal?.prompted;
    const warnAt = req.maxTurns ? req.maxTurns - TURN_BUDGET_WARN : Infinity;
    let steered = resuming && turns >= warnAt;
    const usage = { input: 0, output: 0, cacheRead: 0, cost: 0, ...journal?.usage };
    // Pi 的 input 不含命中缓存的部分：实测 cacheRead 占 prompt 的 72%，漏掉它会少报约 70%。
    const collect = (u: any) => addUsage(usage, u);

    const unsubscribe = session.subscribe((event: any) => {
      bridge(event);
      // 每条 assistant 消息的 usage 只在 message_end 计一次。此前对 message_start / 每个
      // message_update / message_end / turn_end 都累加同一条消息的 usage，实测严重虚高。
      if (event?.type === "message_end" && event?.message?.role === "assistant") {
        collect(event.message.usage);
        const u = event.message.usage;
        if (u && !downgraded) {
          const ctx = (u.input ?? 0) + (u.cacheRead ?? 0) + (u.cacheWrite ?? 0) + (u.output ?? 0);
          const lower = downgradeThinking(thinkingLevel, ctx, downgradeAt);
          if (lower && session.setThinkingLevel) { downgraded = true; session.setThinkingLevel(lower); }
        }
        lastStop = event.message.stopReason;
        lastError = event.message.errorMessage;
      }
      if (event?.type === "turn_end") {
        turns++;
        // 轮次预算 Steering：实测 4/4 长任务撞上限、3/3 实现任务没来得及写 results_summary.md。
        // 剩 TURN_BUDGET_WARN 轮时插入一条 steer，让模型停止探索、先落盘交付物。
        if (req.maxTurns && !steered && turns >= warnAt && turns < req.maxTurns && session.steer) {
          steered = true;
          void session.steer(turnBudgetMessage(req.maxTurns - turns)).catch(() => undefined);
        }
        if (req.maxTurns && turns >= req.maxTurns) { turnCapped = true; void session.abort(); }
      }
      if (event?.type === "agent_settled") settled = true;
    });

    const onAbort = () => { void session.abort(); };
    if (signal?.aborted) onAbort();   // 取消可能发生在 session 创建之前
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      if (req.journal && !journal?.started) sessionManager?.appendCustomEntry?.(CALL_ENTRY, { call });
      await session.prompt(resuming
        ? resumeMessage(steered && req.maxTurns ? req.maxTurns - turns : undefined) : req.task);
      if (signal?.aborted) await session.waitForIdle();
      // 重试耗尽后最后一条 assistant 消息仍是 error：如实失败，交给调度器标 failed。
      // 此前这里静默返回空结果，首轮实测 9 个会话全部出错，流水线却报告 completed。
      // 轮次上限触发的 abort 也会留下 stopReason=error 的空消息，不能算模型故障（bench r1 实测误判 4 次）。
      if (!signal?.aborted && !turnCapped && lastStop === "error")
        throw new AgentRunError(taskId, lastError ?? "model call failed after retries", usage);
      const text = session.getLastAssistantText() ?? "";
      // 只有正常结束（含轮次截断）才写完成标记；取消、出错的会话下次从日志接着跑。
      if (req.journal && !signal?.aborted) {
        try { sessionManager?.appendCustomEntry?.(RESULT_ENTRY, { call, text, ...(turnCapped ? { turnCapped } : {}) }); }
        catch { /* 标记写不进去只影响下次能否回放，不影响本次结果 */ }
      }
      return {
        text,
        artifacts: diffFiles(req.cwd, before),
        usage,
        settled,
        ...(turnCapped ? { turnCapped } : {}),
        ...(resuming ? { resumed: true } : {}),
        ...(submitted ? { submitted } : {}),
      };
    } finally {
      signal?.removeEventListener("abort", onAbort);
      unsubscribe();     // 抛错路径也保证
      session.dispose(); // 抛错路径也保证
    }
  }
}
