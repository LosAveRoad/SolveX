import type { SolveXEvent } from "@solvex/core";

/** 只消费兼容子集，新增结构化事件降级为 info，不破坏旧 CLI 体验。 */
export function renderEvent(e: SolveXEvent): string | undefined {
  switch (e.type) {
    case "status": return `\x1b[1;36m${"=".repeat(50)}\n  ${e.message}\n${"=".repeat(50)}\x1b[0m`;
    case "step": return `\x1b[1;33m>>> ${e.message}\x1b[0m`;
    case "done": return `\x1b[1;32m✓ ${e.message}\x1b[0m`;
    case "warn": return `  ⚠ ${e.message}`;
    case "info": return `  ${e.message}`;
    case "error": return `\x1b[1;31m✗ ${e.message}\x1b[0m`;
    case "complete": {
      const r = e.result;
      return `\x1b[1;32m✓ 完成 | 状态=${r.status} | 模型=${r.models.length} | ` +
        `token=${r.totalTokens ?? 0} | 耗时=${(r.elapsedMs / 1000).toFixed(1)}s\x1b[0m`;
    }
    case "barrier": return e.state === "released" ? undefined : `  ⏳ 屏障 ${e.id}: ${e.completed}/${e.total}`;
    case "usage": return undefined; // 顶部条由 WebUI 显示，CLI 不刷屏
    default: return undefined;
  }
}
