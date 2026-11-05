/** Pi SDK 1.5.0 的最小可用接口（按真实 .d.ts 核实）。
 *  本文件是 packages/pi-runtime 之外唯一引用 SDK 的地方；core 零依赖。
 *  延迟动态 import 让单测可注入 FakeSdk 而不加载真实 SDK（含原生依赖）。 */
export type PiSessionLike = {
  subscribe(fn: (event: any) => void): () => void;
  dispose(): void;
  prompt(text: string): Promise<void>;
  abort(): Promise<void>;
  waitForIdle(): Promise<void>;
  getLastAssistantText(): string | undefined;
  setModel(model: any): Promise<void>;
  setThinkingLevel(level: any): void;
};

export type PiSdk = {
  createAgentSession(options: any): Promise<{ session: PiSessionLike }>;
  DefaultResourceLoader: new (options: any) => { reload(): Promise<void> };
  SessionManager: { inMemory(): unknown; create(cwd: string): unknown };
  SettingsManager: { create(...args: any[]): unknown };
  getAgentDir(): string;
  ModelRuntime: { create(options: any): Promise<any> };
  defineTool(tool: any): any;
};

export async function loadRealSdk(): Promise<PiSdk> {
  const m = await import("@earendil-works/pi-coding-agent");
  return m as unknown as PiSdk;
}
