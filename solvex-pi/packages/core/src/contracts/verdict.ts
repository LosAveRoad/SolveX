export type VerdictStatus = "satisfied" | "needs_revision" | "unknown";
export type Verdict = {
  status: VerdictStatus;
  source: "structured" | "legacy" | "none";
  issuesFound?: string;
  fixInstructions?: string;
  summaryPath?: string;
  warn?: string;
};
