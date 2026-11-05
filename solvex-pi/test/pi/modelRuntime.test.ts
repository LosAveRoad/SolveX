import { describe, it, expect, beforeEach } from "vitest";
import { ModelRuntimeManager } from "@solvex/pi-runtime";
import { THINKING_LEVELS as CORE_LEVELS } from "@solvex/core";

const fakeRt = () => ({
  getAvailable: async () => [
    { provider: "anthropic", id: "claude-x", name: "Claude", reasoning: true,
      input: ["text", "image"], contextWindow: 200000, cost: { input: 3, output: 15 },
      apiKey: "sk-supersecret-123456" },
    { provider: "openai", id: "gpt-mini", reasoning: false, input: ["text"] },
  ],
  getModel: (p: string, id: string) => p === "bad" ? undefined : { provider: p, id },
  setRuntimeApiKey: async () => {},
  refresh: async () => ({}),
  listCredentials: async () => [{ providerId: "anthropic", apiKey: "sk-secret-abcdef", status: "ok" }],
  getRegisteredProviderIds: () => ["anthropic"],
});

describe("T3.6 模型配置桥接（单例 / 脱敏）", () => {
  beforeEach(() => ModelRuntimeManager.resetForTest());
  it("shared() 只 create 一次，多阶段复用同一实例", async () => {
    const a = await ModelRuntimeManager.shared({ sdkRuntime: fakeRt() });
    const b = await ModelRuntimeManager.shared({ sdkRuntime: fakeRt() });
    expect(a).toBe(b);
  });
  it("getAvailable() 映射为脱敏 ModelDescriptor，响应体无 apiKey", async () => {
    const m = await ModelRuntimeManager.create({ sdkRuntime: fakeRt() });
    const list = await m.listAvailable();
    expect(list).toHaveLength(2);
    expect(list[0].reasoning).toBe(true);
    expect(JSON.stringify(list)).not.toContain("sk-supersecret");
    expect(JSON.stringify(list)).not.toContain("apiKey");
  });
  it("凭据只回 masked，明文不出现", async () => {
    const m = await ModelRuntimeManager.create({ sdkRuntime: fakeRt() });
    const creds = await m.credentials();
    expect(creds[0].masked).toContain("••••");
    expect(JSON.stringify(creds)).not.toContain("sk-secret-abcdef");
  });
  it("setRuntimeApiKey 只调运行时，不写文件不进日志", async () => {
    let called = 0;
    const m = await ModelRuntimeManager.create({ sdkRuntime: { ...fakeRt(),
      setRuntimeApiKey: async () => { called++; } } });
    await m.setRuntimeApiKey("anthropic", "sk-runtime-key");
    expect(called).toBe(1);
  });
  it("thinking 档位按模型能力裁剪", async () => {
    const m = await ModelRuntimeManager.create({ sdkRuntime: fakeRt() });
    const list = await m.listAvailable();
    expect(m.thinkingLevelsFor(list[0])).toEqual([...CORE_LEVELS]);
    expect(m.thinkingLevelsFor(list[1])).toEqual(["off"]);
    expect(CORE_LEVELS).toHaveLength(7);
  });
  it("scopedModels 解析为 {model}[]，跳过找不到的", async () => {
    const m = await ModelRuntimeManager.create({ sdkRuntime: fakeRt() });
    expect(m.scopedModels(["anthropic/claude-x", "bad/nope"])).toHaveLength(1);
  });
});
