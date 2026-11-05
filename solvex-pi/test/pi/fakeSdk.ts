import { vi } from "vitest";
import type { PiSdk } from "@solvex/pi-runtime";

export function makeFakeSdk(opts: { promptImpl?: (emit: (e: any) => void) => Promise<void> } = {}) {
  const loaderOptions: any[] = [];
  const createOptions: any[] = [];
  let listener: ((e: any) => void) | undefined;
  const unsubscribe = vi.fn();
  const session = {
    subscribe: vi.fn((fn: (e: any) => void) => { listener = fn; return unsubscribe; }),
    dispose: vi.fn(),
    prompt: vi.fn(async (_text: string) => {
      if (opts.promptImpl) await opts.promptImpl((e) => listener?.(e));
      else listener?.({ type: "agent_settled", aborted: false });
    }),
    abort: vi.fn(async () => {}),
    waitForIdle: vi.fn(async () => {}),
    getLastAssistantText: vi.fn(() => "final answer"),
    setModel: vi.fn(), setThinkingLevel: vi.fn(),
  };
  class DefaultResourceLoader {
    constructor(public options: any) { loaderOptions.push(options); }
    async reload() {}
  }
  const sdk = {
    createAgentSession: vi.fn(async (o: any) => { createOptions.push(o); return { session }; }),
    DefaultResourceLoader,
    SessionManager: { inMemory: vi.fn(() => ({ kind: "inMemory" })), create: vi.fn(() => ({ kind: "file" })) },
    SettingsManager: { create: vi.fn(() => ({ kind: "settings" })) },
    getAgentDir: () => "/tmp/pi-agent",
    ModelRuntime: { create: vi.fn(async () => ({})) },
    defineTool: (t: any) => t,
  } as unknown as PiSdk;
  return { sdk, session, loaderOptions, createOptions, unsubscribe };
}
