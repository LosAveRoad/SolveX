import type { Issue } from "../events/types.js";

export const REQUIRED_SUMMARY_SECTIONS = [
  "## Key Numerical Results", "## Sanity Checks", "## Model Parameters",
  "## Data Files Generated", "## Figures", "## Issues or Limitations",
] as const;

/** B5：results_summary 格式不统一是旧版根因链起点，这里做结构化校验。 */
export function validateSummaryShape(text: string): Issue[] {
  const issues: Issue[] = [];
  for (const h of REQUIRED_SUMMARY_SECTIONS) {
    if (!text.includes(h)) issues.push({ code: "MISSING_SUMMARY_SECTION", severity: "warn", evidence: h });
  }
  return issues;
}
