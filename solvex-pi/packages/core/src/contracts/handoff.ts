import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export type Handoff = {
  status: "satisfied" | "needs_revision";
  issues?: string[];
  fixInstructions?: string;
  summaryPath?: string;
};

export function validateHandoff(v: unknown): Handoff | null {
  if (!v || typeof v !== "object") return null;
  const o = v as any;
  if (o.status !== "satisfied" && o.status !== "needs_revision") return null;
  if (o.issues !== undefined && !Array.isArray(o.issues)) return null;
  return { status: o.status, issues: o.issues?.map(String),
    fixInstructions: o.fixInstructions === undefined ? undefined : String(o.fixInstructions),
    summaryPath: o.summaryPath === undefined ? undefined : String(o.summaryPath) };
}

export function readHandoff(dir: string): Handoff | null {
  const f = join(dir, "handoff.json");
  if (!existsSync(f)) return null;
  try { return validateHandoff(JSON.parse(readFileSync(f, "utf-8"))); }
  catch { return null; }
}
