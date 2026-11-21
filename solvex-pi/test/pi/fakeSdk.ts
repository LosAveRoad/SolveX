import { vi } from "vitest";
import { existsSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import type { PiSdk } from "@solvex/pi-runtime";

/** 与 Pi SessionManager 同一落盘语义的最小实现：出现 user/assistant 消息后才建文件，之后逐条追加。 */
export class FakeJournalSM {
  entries: any[];
  private flushed: boolean;
  private n = 0;
  constructor(public path: string, cwd: string) {
    if (existsSync(path)) {
      this.entries = readFileSync(path, "utf-8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
      this.flushed = true;
    } else {
      this.entries = [{ type: "session", version: 3, id: "fake", cwd }];
      this.flushed = false;
    }
  }
  private append(e: any) {
    const last = this.entries[this.entries.length - 1];
    const entry = { ...e, id: `e${Date.now().toString(36)}${this.n++}`, parentId: last?.type === "session" ? null : last?.id ?? null };
    this.entries.push(entry);
    if (!this.flushed) {
      if (!this.entries.some((x) => x.type === "message")) return;
      writeFileSync(this.path, this.entries.map((x) => JSON.stringify(x)).join("\n") + "\n");
      this.flushed = true;
    } else appendFileSync(this.path, JSON.stringify(entry) + "\n");
  }
  appendMessage(message: any) { this.append({ type: "message", message }); }
  appendCustomEntry(customType: string, data?: unknown) { this.append({ type: "custom", customType, data }); }
}

export function makeFakeSdk(opts: { promptImpl?: (emit: (e: any) => void) => Promise<void> } = {}) {
  const loaderOptions: any[] = [];
  const createOptions: any[] = [];
  let listener: ((e: any) => void) | undefined;
  let sm: any;
  // 真实 Pi 在 message_end 时把消息写进 SessionManager；这里同样转写，日志测试才有内容可回放。
  const emit = (e: any) => {
    if (e?.type === "message_end" && sm?.appendMessage) sm.appendMessage(e.message);
    listener?.(e);
  };
  const unsubscribe = vi.fn();
  const session = {
    subscribe: vi.fn((fn: (e: any) => void) => { listener = fn; return unsubscribe; }),
    dispose: vi.fn(),
    prompt: vi.fn(async (text: string) => {
      sm?.appendMessage?.({ role: "user", content: text });
      if (opts.promptImpl) await opts.promptImpl(emit);
      else listener?.({ type: "agent_settled", aborted: false });
    }),
    abort: vi.fn(async () => {}),
    steer: vi.fn(async (_text: string) => {}),
    waitForIdle: vi.fn(async () => {}),
    getLastAssistantText: vi.fn(() => "final answer"),
    setModel: vi.fn(), setThinkingLevel: vi.fn(),
  };
  const settings = { kind: "settings", overrides: [] as any[], applyOverrides(o: any) { this.overrides.push(o); } };
  class DefaultResourceLoader {
    constructor(public options: any) { loaderOptions.push(options); }
    async reload() {}
  }
  const sdk = {
    createAgentSession: vi.fn(async (o: any) => { createOptions.push(o); sm = o.sessionManager; return { session }; }),
    DefaultResourceLoader,
    SessionManager: { inMemory: vi.fn(() => ({ kind: "inMemory" })), create: vi.fn(() => ({ kind: "file" })),
                      open: vi.fn((path: string, _dir?: string, cwd?: string) => new FakeJournalSM(path, cwd ?? "")) },
    SettingsManager: { create: vi.fn(() => settings) },
    getAgentDir: () => "/tmp/pi-agent",
    ModelRuntime: { create: vi.fn(async () => ({})) },
    defineTool: (t: any) => t,
  } as unknown as PiSdk;
  return { sdk, session, settings, loaderOptions, createOptions, unsubscribe };
}
