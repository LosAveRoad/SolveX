// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  formatTokens, formatCost, buildUsageBar, buildFileTree, normalizeArtifacts,
  toFormEntries, buildRunFormData, buildFetchOptions, downloadUrl, groupDigits,
} from "../../apps/web/public/modules/artifacts.js";
import { describe, it, expect } from "vitest";

describe("T5.20 artifacts 产物 / 顶部用量条 / startRun 的 FormData 修复", () => {
  it("formatTokens / formatCost / groupDigits 格式化", () => {
    expect(formatTokens(12400)).toBe("12.4K");
    expect(formatTokens(8100)).toBe("8.1K");
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(2500000)).toBe("2.5M");
    expect(formatCost(3.42)).toBe("¥3.42");
    expect(groupDigits(1842)).toBe("1,842");
  });

  it("buildUsageBar 顶部条实时显示模型 / thinking / token / ¥", () => {
    const state = {
      status: "running",
      model: { provider: "anthropic", model: "claude-x", thinkingLevel: "high" },
      config: {},
      usage: { global: { input: 12400, output: 8100, totalTokens: 20500, cost: 3.42 } },
    };
    const bar = buildUsageBar(state);
    expect(bar.model).toBe("anthropic/claude-x");
    expect(bar.thinking).toBe("high");
    expect(bar.input).toBe("12.4K");
    expect(bar.output).toBe("8.1K");
    expect(bar.tokens).toBe("20.5K");
    expect(bar.cost).toBe("¥3.42");
    expect(buildUsageBar({}).status).toBe("idle");
  });

  it("buildFileTree 从扁平路径还原真实文件树", () => {
    const tree = buildFileTree([
      "01_modeling/master_plan.md",
      "02_programming/model_1/results_summary.md",
      "02_programming/model_1/figures/fig1.png",
      "04_paper/main.tex",
    ]);
    expect(tree.children.map((c) => c.name)).toEqual(["01_modeling", "02_programming", "04_paper"]);
    const modeling = tree.children.find((c) => c.name === "01_modeling");
    expect(modeling.children[0].type).toBe("file");
    expect(modeling.children[0].path).toBe("01_modeling/master_plan.md");
    const prog = tree.children.find((c) => c.name === "02_programming");
    expect(prog.type).toBe("dir");
    expect(prog.children[0].name).toBe("model_1");
    expect(buildFileTree([]).children).toEqual([]);
  });

  it("normalizeArtifacts 兼容数组 / files / tree 多种形态", () => {
    expect(normalizeArtifacts(["a/b.md", "c.tex"])).toEqual(["a/b.md", "c.tex"]);
    expect(normalizeArtifacts({ files: [{ path: "x.md" }, { path: "y.md" }] })).toEqual(["x.md", "y.md"]);
    expect(normalizeArtifacts({ tree: ["m.md"] })).toEqual(["m.md"]);
    expect(normalizeArtifacts(null)).toEqual([]);
  });

  it("toFormEntries 字段：text + files[] + 可选 concurrency / strict", () => {
    const e = toFormEntries({ text: "问题", files: ["a.csv", "b.csv"], concurrency: 3, strict: true });
    expect(e).toContainEqual(["text", "问题"]);
    expect(e.filter(([k]) => k === "files[]")).toHaveLength(2);
    expect(e).toContainEqual(["concurrency", "3"]);
    expect(e).toContainEqual(["strict", "true"]);
    // 未提供的可选字段不出现
    const e2 = toFormEntries({ text: "x", files: [] });
    expect(e2.map(([k]) => k)).toEqual(["text"]);
  });

  it("buildRunFormData 产出真正的 FormData，含 text 与 files[]", () => {
    const fd = buildRunFormData({ text: "问题", files: ["a.csv"], concurrency: 2, strict: false });
    expect(fd instanceof FormData).toBe(true);
    expect(fd.get("text")).toBe("问题");
    expect(fd.getAll("files[]")).toEqual(["a.csv"]);
    expect(fd.get("concurrency")).toBe("2");
    expect(fd.get("strict")).toBe("false");
  });

  it("关键修复：buildFetchOptions 绝不手动设置 Content-Type / headers", () => {
    const fd = buildRunFormData({ text: "x" });
    const opts = buildFetchOptions(fd);
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(fd);
    expect(opts.headers).toBeUndefined();               // 不设 headers
    expect((opts.headers || {})["Content-Type"]).toBeUndefined(); // 让浏览器自动加 multipart boundary
    expect(JSON.stringify(opts)).not.toContain("Content-Type");
  });

  it("downloadUrl 构造 ZIP 下载地址", () => {
    expect(downloadUrl("sess-1")).toBe("/api/download/sess-1");
    expect(downloadUrl("a b")).toBe("/api/download/a%20b");
  });
});
