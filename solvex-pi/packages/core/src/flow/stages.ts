import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { WorkspaceInfo } from "../workspace/index.js";
import { modelDirName } from "../workspace/paths.js";
import { DIR } from "../workspace/paths.js";
import { summarizeArtifacts } from "../gates/artifacts.js";

/** R11 写安全：all_results_summary.md 只由本函数（纯代码）在屏障后生成，任何 LLM 都不写它。
 *  ADR-0009：除 results_summary.md 外，附带每个模型目录的产物扫描结果，
 *  让 P4 在 prompt 里就能拿到真实 CSV 的路径与数值摘要（模型无法自己枚举目录）。 */
export function aggregate(ws: WorkspaceInfo, models: string[]): { path: string; content: string } {
  const out: string[] = ["# All Models Results Summary", "",
    `Total models implemented: ${models.length}`, ""];
  for (const m of models) {
    const dir = modelDirName(m);
    const modelDir = join(ws.paths.programming, dir);
    out.push(`## ${m}`, "");
    const summary = join(modelDir, "results_summary.md");
    out.push(existsSync(summary) ? readFileSync(summary, "utf-8") : "⚠ No results_summary.md", "", "---", "");
    const figDir = join(modelDir, "figures");
    if (existsSync(figDir)) {
      const figs = readdirSync(figDir).filter((f) => /\.(png|jpe?g|svg|pdf)$/i.test(f));
      if (figs.length) {
        out.push("### Figures", "");
        for (const f of figs) out.push(`- ${dir}/figures/${f}`);
        out.push("");
      }
    }
    out.push(summarizeArtifacts(modelDir), "", "---", "");
  }
  const content = out.join("\n");
  const path = join(ws.paths.programming, "all_results_summary.md");
  writeFileSync(path, content);
  return { path, content };
}

export function figureInfo(ws: WorkspaceInfo, models: string[]): string {
  const parts: string[] = [];
  for (const m of models) {
    const dir = modelDirName(m);
    const figDir = join(ws.paths.programming, dir, "figures");
    if (!existsSync(figDir)) continue;
    const figs = readdirSync(figDir).filter((f) => /\.(png|jpe?g|svg|pdf)$/i.test(f));
    if (!figs.length) continue;
    parts.push(`${m} figures (use ../02_programming/${dir}/figures/):`);
    for (const f of figs) parts.push(`  - ${f}`);
  }
  return parts.length ? parts.join("\n") : "No figures generated.";
}
