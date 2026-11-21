import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@solvex/core": r("./packages/core/src/index.ts"),
      "@solvex/pi-runtime": r("./packages/pi-runtime/src/index.ts"),
      "@solvex/web": r("./apps/web/src/server.ts"),
      "@earendil-works/pi-coding-agent": r("./packages/pi-runtime/node_modules/@earendil-works/pi-coding-agent/dist/index.js"),
      "@earendil-works/pi-mcp/testing": r("./packages/pi-runtime/node_modules/@earendil-works/pi-mcp/dist/testing/index.js"),
      "@earendil-works/pi-mcp": r("./packages/pi-runtime/node_modules/@earendil-works/pi-mcp/dist/index.js"),
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    // Web 端点测试会启动真实 Fastify + 动态加载 Pi SDK，高并行下冷启动会拖垮 SSE / 轮询用例。
    // 限制 worker 数换取可重复的通过率；单测本身仍然并行跑在不同文件间。
    maxWorkers: 2,
    // 真实 Pi SDK 首次 import（约 7.8MB ESM）+ ModelRuntime.create() 冷启动实测 5s；
    // 两个 worker 同时加载时偶发 30s+ 抖动，留足余量避免环境造成的假红。
    testTimeout: 60_000,
    hookTimeout: 60_000,
    coverage: { provider: "v8", include: ["packages/*/src/**", "apps/*/src/**"] },
  },
});
