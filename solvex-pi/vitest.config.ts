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
    },
  },
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    coverage: { provider: "v8", include: ["packages/*/src/**", "apps/*/src/**"] },
  },
});
