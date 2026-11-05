import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

/** B2/E4 修复：兜底摘要只写结构化占位，绝不塞 <think/> 或原始工具 JSON。 */
export function ensureSummary(modelDir: string, modelName: string): string {
  const body = [
    `# ${modelName} Results Summary (auto-generated)`, "",
    "## Status", "⚠ Agent did not write results_summary.md — no validated results available.", "",
    "## Key Numerical Results", "⚠ Not available.", "",
    "## Sanity Checks", "⚠ NOT PERFORMED — agent did not validate.", "",
    "## Model Parameters", "⚠ Not available.", "",
    "## Data Files Generated", "⚠ None.", "",
    "## Figures", "⚠ None generated.", "",
    "## Issues or Limitations", "This is a structured placeholder, not a model result.", "",
  ].join("\n");
  mkdirSync(modelDir, { recursive: true });
  writeFileSync(join(modelDir, "results_summary.md"), body);
  return body;
}
