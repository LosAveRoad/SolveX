import { existsSync, readFileSync } from "node:fs";
import { readHandoff } from "../contracts/handoff.js";
import type { Verdict } from "../contracts/verdict.js";

function cut(text: string, from: string, to?: string): string | undefined {
  const i = text.indexOf(from);
  if (i < 0) return undefined;
  const rest = text.slice(i + from.length);
  const j = to ? rest.indexOf(to) : -1;
  return (j >= 0 ? rest.slice(0, j) : rest).trim();
}

/** 双轨（ADR-03 / D3）：优先 handoff.json，回退旧 VERIFICATION_RESULT 文本标记。 */
export function parseVerdict(opts: { text?: string; dir?: string; reviewPath?: string }): Verdict {
  const text = [opts.text ?? "", opts.reviewPath && existsSync(opts.reviewPath)
    ? readFileSync(opts.reviewPath, "utf-8") : ""].join("\n");
  const handoff = opts.dir ? readHandoff(opts.dir) : null;

  const legacyMatch = text.match(/VERIFICATION_RESULT:\s*(SATISFIED|NEEDS_REVISION)/i);
  const legacy = legacyMatch?.[1]?.toLowerCase() as "satisfied" | "needs_revision" | undefined;
  const issuesFound = cut(text, "## Issues Found:", "## Fix Instructions:");
  const fixInstructions = cut(text, "## Fix Instructions:");

  if (handoff) {
    const conflict = legacy && legacy !== handoff.status;
    return {
      status: handoff.status,
      source: "structured",
      issuesFound: handoff.issues?.join("\n") ?? issuesFound,
      fixInstructions: handoff.fixInstructions || fixInstructions,
      summaryPath: handoff.summaryPath,
      ...(conflict ? { warn: `handoff.json(${handoff.status}) 与文本标记(${legacy}) 冲突，以结构化为准` } : {}),
    };
  }
  if (legacy) return { status: legacy, source: "legacy", issuesFound, fixInstructions };
  return { status: "unknown", source: "none" };
}
