// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  groupByProvider, searchModels, maskApiKey, safeCredential, sanitizeConfig,
  filterThinkingLevels, capabilityTags, setDefault, assignToPhase, addScoped,
  buildSavePayload, normalizeModelResponse, THINKING_LEVELS, PHASES,
} from "../../apps/web/public/modules/models.js";
import { describe, it, expect } from "vitest";

const models = [
  { provider: "anthropic", id: "claude-opus", name: "Opus", reasoning: true, input: ["text", "image"], contextLimit: 200000, price: { input: 15, output: 75 }, available: true },
  { provider: "anthropic", id: "claude-haiku", name: "Haiku", reasoning: false, input: ["text"], contextLimit: 200000, available: true },
  { provider: "openai", id: "gpt-o3", name: "o3", reasoning: true, input: ["text"], contextLimit: 128000, price: { input: 2, output: 8 }, available: false },
];

describe("T5.17 models 模型配置中心 / 分组·搜索·脱敏·档位", () => {
  it("groupByProvider 按 provider 分组", () => {
    const g = groupByProvider(models);
    expect(Object.keys(g)).toEqual(["anthropic", "openai"]);
    expect(g.anthropic).toHaveLength(2);
    expect(g.openai).toHaveLength(1);
    expect(groupByProvider([])).toEqual({});
  });

  it("searchModels 按 id / name / provider 大小写不敏感；空查询返回全部", () => {
    expect(searchModels(models, "opus").map((m) => m.id)).toEqual(["claude-opus"]);
    expect(searchModels(models, "ANTHROPIC")).toHaveLength(2);
    expect(searchModels(models, "o3").map((m) => m.id)).toEqual(["gpt-o3"]);
    expect(searchModels(models, "  ")).toHaveLength(3);
    expect(searchModels(models, "nomatch")).toHaveLength(0);
  });

  it("maskApiKey 脱敏：保留首尾、隐藏明文；已 masked 原样返回", () => {
    const masked = maskApiKey("sk-abcdefgh1234");
    expect(masked).not.toContain("abcdefgh");
    expect(masked.endsWith("1234")).toBe(true);
    expect(maskApiKey("sk-••••1234")).toBe("sk-••••1234");
    expect(maskApiKey("")).toBe("");
  });

  it("safeCredential 只暴露 masked，绝不返回明文 apiKey", () => {
    const c = safeCredential({ provider: "openai", source: "env", status: "ok", apiKey: "sk-super-secret-9999" });
    expect(c.apiKey).toBeUndefined();
    expect(c.masked).not.toContain("super-secret");
    expect(JSON.stringify(c)).not.toContain("sk-super-secret-9999");
    expect(c).toMatchObject({ provider: "openai", source: "env", status: "ok" });
  });

  it("sanitizeConfig 递归剔除任何明文密钥字段", () => {
    const cfg = {
      defaults: { model: "x" },
      credentials: [{ provider: "a", apiKey: "sk-PLAINTEXT-1234", masked: "sk-••••1234" }],
      endpoints: [{ baseUrl: "http://x", apiKey: "$ENV:KEY", token: "abc" }],
      nested: { password: "pw", api_key: "k" },
    };
    const safe = sanitizeConfig(cfg);
    const json = JSON.stringify(safe);
    expect(json).not.toContain("sk-PLAINTEXT-1234");
    expect(json).not.toContain("\"apiKey\"");
    expect(json).not.toContain("\"password\"");
    expect(json).not.toContain("\"token\"");
    expect(safe.defaults.model).toBe("x");                // 非敏感字段保留
    expect(safe.credentials[0].masked).toBe("sk-••••1234"); // masked 保留
    expect(cfg.credentials[0].apiKey).toBe("sk-PLAINTEXT-1234"); // 原对象未被改
  });

  it("filterThinkingLevels 按 reasoning 能力裁剪：不支持 → ['off']", () => {
    expect(filterThinkingLevels(models[0])).toEqual(THINKING_LEVELS);
    expect(filterThinkingLevels(models[1])).toEqual(["off"]);
    expect(filterThinkingLevels(null)).toEqual(["off"]);
    expect(filterThinkingLevels({ reasoning: true, thinkingLevels: ["off", "low", "high"] })).toEqual(["off", "low", "high"]);
  });

  it("capabilityTags 输出 reasoning / vision / 上下文 / 价格", () => {
    const tags = capabilityTags(models[0]);
    expect(tags).toContain("reasoning");
    expect(tags).toContain("vision");
    expect(tags.some((t) => t.includes("200K"))).toBe(true);
    expect(tags.some((t) => t.includes("¥"))).toBe(true);
    expect(capabilityTags(models[1])).not.toContain("reasoning");
  });

  it("setDefault / assignToPhase / addScoped 纯函数编辑配置", () => {
    let cfg = {};
    cfg = setDefault(cfg, "anthropic", "claude-opus");
    expect(cfg.defaults).toMatchObject({ provider: "anthropic", model: "claude-opus" });
    cfg = assignToPhase(cfg, "P2_IMPL", "openai", "gpt-o3");
    expect(cfg.byPhase.P2_IMPL).toMatchObject({ provider: "openai", model: "gpt-o3" });
    cfg = addScoped(cfg, "anthropic/claude-opus");
    cfg = addScoped(cfg, "anthropic/claude-opus"); // 去重
    expect(cfg.scopedModels).toEqual(["anthropic/claude-opus"]);
    expect(PHASES).toContain("P2_IMPL");
  });

  it("buildSavePayload 输出已净化载荷（无明文密钥）", () => {
    const payload = buildSavePayload({
      defaults: { model: "x", thinkingLevel: "high", apiKey: "sk-SHOULD-NOT-APPEAR" },
      byPhase: {}, scopedModels: [],
    });
    expect(payload.thinkingLevel).toBe("high");
    expect(JSON.stringify(payload)).not.toContain("sk-SHOULD-NOT-APPEAR");
    expect(payload.defaults.apiKey).toBeUndefined();
  });

  it("normalizeModelResponse 规整响应并净化凭据", () => {
    const norm = normalizeModelResponse({
      models,
      config: { defaults: { model: "x" } },
      credentials: [{ provider: "a", source: "env", status: "ok", apiKey: "sk-SECRET", masked: "sk-••••9999" }],
      endpoints: [{ baseUrl: "http://x", apiKey: "$ENV:KEY" }],
    });
    expect(norm.models).toHaveLength(3);
    expect(norm.config.defaults.model).toBe("x");
    expect(norm.credentials[0].masked).toBe("sk-••••9999");
    expect(JSON.stringify(norm)).not.toContain("sk-SECRET");
    expect(JSON.stringify(norm.endpoints)).not.toContain("\"apiKey\"");
  });
});
