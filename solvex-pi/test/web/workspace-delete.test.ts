import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, existsSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "@solvex/web";
import { testPaths } from "./helpers.js";

let app: any;
let root: string;
let wsRoot: string;

beforeAll(async () => {
  root = mkdtempSync(join(tmpdir(), "solvex-delete-"));
  wsRoot = join(root, "workspaces");
  const paths = testPaths();
  app = await createServer({ sessionRoot: paths.sessionRoot, workspaceRoot: wsRoot,
    configPath: paths.configPath, modelsPath: paths.modelsPath,
    mcpConfigPath: paths.mcpConfigPath, pingMs: 200 });
  await app.ready();
});

afterAll(async () => {
  await app.close();
  rmSync(root, { recursive: true, force: true });
});

async function newWorkspace(name = "待删除"): Promise<string> {
  const r = await app.inject({ method: "POST", url: "/api/workspaces", payload: { name } });
  expect(r.statusCode).toBe(201);
  return r.json().id as string;
}

/** 直接造历史 run 目录，避免启动真实模型调用。 */
function seedRun(workspaceId: string, runId: string): string {
  const dir = join(wsRoot, workspaceId, "runs", runId);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, ".solvex-meta.json"), JSON.stringify({
    id: runId, problem: "seed", status: "completed",
    created_at: new Date().toISOString(), workspaceId,
  }));
  return dir;
}

describe("删除工作区与运行记录", () => {
  it("删除空工作区：目录与列表都消失", async () => {
    const id = await newWorkspace();
    const dir = join(wsRoot, id);
    expect(existsSync(dir)).toBe(true);
    const del = await app.inject({ method: "DELETE", url: `/api/workspaces/${id}` });
    expect(del.statusCode).toBe(200);
    expect(existsSync(dir)).toBe(false);
    const list = (await app.inject({ method: "GET", url: "/api/workspaces" })).json();
    expect(list.some((w: any) => w.id === id)).toBe(false);
  });

  it("删除单次运行只影响目标 run，其它 run 保留", async () => {
    const id = await newWorkspace();
    const a = seedRun(id, "run-a");
    const b = seedRun(id, "run-b");
    const before = (await app.inject({ method: "GET", url: `/api/workspaces/${id}/runs` })).json();
    expect(before.map((r: any) => r.id)).toEqual(expect.arrayContaining(["run-a", "run-b"]));

    const del = await app.inject({ method: "DELETE", url: `/api/workspaces/${id}/runs/run-a` });
    expect(del.statusCode).toBe(200);
    expect(existsSync(a)).toBe(false);
    expect(existsSync(b)).toBe(true);

    const after = (await app.inject({ method: "GET", url: `/api/workspaces/${id}/runs` })).json();
    expect(after.some((r: any) => r.id === "run-a")).toBe(false);
    expect(after.some((r: any) => r.id === "run-b")).toBe(true);
  });

  it("删除工作区会连带删除其下全部 run", async () => {
    const id = await newWorkspace();
    seedRun(id, "run-c");
    seedRun(id, "run-d");
    const del = await app.inject({ method: "DELETE", url: `/api/workspaces/${id}` });
    expect(del.statusCode).toBe(200);
    expect(existsSync(join(wsRoot, id))).toBe(false);
  });

  it("非法工作区 ID / 不存在的 run 返回 404", async () => {
    const bad = await app.inject({ method: "DELETE", url: "/api/workspaces/not-a-uuid" });
    expect(bad.statusCode).toBe(404);
    const id = await newWorkspace();
    const missing = await app.inject({ method: "DELETE", url: `/api/workspaces/${id}/runs/nope` });
    expect(missing.statusCode).toBe(404);
  });
});
