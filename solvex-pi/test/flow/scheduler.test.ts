import { describe, it, expect } from "vitest";
import { buildDag, ready, schedule, type SchedTask } from "@solvex/core";

const models = ["Model 1", "Model 2", "Model 3", "Model 4", "Model 5"];
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const task = (id: string, dependsOn: string[] = [], run?: (s?: AbortSignal) => Promise<void>): SchedTask => ({
  id, taskId: id, label: id, phase: 2, kind: "task", dependsOn, run,
});

describe("T2.9 并行 DAG 调度器（D2，零 Pi 依赖）", () => {
  it("① P1 完成后 ready 一次性返回 5 个 P2-IMPL（无依赖即并行）", () => {
    const dag = buildDag(models);
    const settled = new Set(["P1", "barrier-master-plan"]);
    const r = ready(dag, settled, new Set(), new Set()).filter((n) => n.id.startsWith("P2-IMPL:"));
    expect(r).toHaveLength(5);
    expect(r.every((n) => n.dependsOn.length === 1)).toBe(true);
  });

  it("② concurrency=3 时同时运行任务数恒 ≤3", async () => {
    let active = 0, peak = 0;
    const tasks = models.map((_, i) => task(`t${i}`, [], async () => {
      active++; peak = Math.max(peak, active);
      await delay(20); active--;
    }));
    const r = await schedule(tasks, { concurrency: 3 });
    expect(r.peakActive).toBeLessThanOrEqual(3);
    expect(peak).toBe(3);
    expect(r.done).toHaveLength(5);
  });

  it("③ 屏障在全部完成前 waiting，全部完成后 released 才派发后续", async () => {
    const barriers: { st: string; c: number; t: number }[] = [];
    let afterRan = false;
    const tasks: SchedTask[] = [
      task("a", [], async () => { await delay(10); }),
      task("b", [], async () => { await delay(35); }),
      { id: "bar", taskId: "bar", label: "bar", phase: 2, kind: "barrier", dependsOn: ["a", "b"] },
      task("after", ["bar"], async () => { afterRan = true; }),
    ];
    const r = await schedule(tasks, { concurrency: 3,
      onBarrier: (_id, st, c, t) => barriers.push({ st, c, t }) });
    expect(r.done).toContain("bar");
    expect(afterRan).toBe(true);
    expect(barriers.some((b) => b.st === "waiting" && b.t === 2)).toBe(true);
    expect(barriers.some((b) => b.st === "released" && b.c === 2 && b.t === 2)).toBe(true);
  });

  it("④ 单任务 failed 不取消兄弟，屏障处汇总", async () => {
    let sibling = false;
    const tasks: SchedTask[] = [
      task("bad", [], async () => { throw new Error("boom"); }),
      task("good", [], async () => { sibling = true; }),
      { id: "bar", taskId: "bar", label: "bar", phase: 2, kind: "barrier", dependsOn: ["bad", "good"] },
    ];
    const r = await schedule(tasks, { concurrency: 2 });
    expect(r.failed).toEqual(["bad"]);
    expect(r.done).toContain("good");
    expect(r.done).toContain("bar");
    expect(sibling).toBe(true);
  });

  it("⑤ AbortSignal 触发后不再派发新任务", async () => {
    const ac = new AbortController();
    let dispatched = 0;
    const tasks = models.map((_, i) => task(`t${i}`, [], async (sig) => {
      dispatched++;
      if (i === 0) ac.abort();
      if (sig?.aborted) throw new Error("aborted");
      await delay(5);
    }));
    const r = await schedule(tasks, { concurrency: 1, signal: ac.signal });
    expect(r.aborted).toBe(true);
    expect(dispatched).toBe(1);
  });

  it("⑥ concurrency=1 顺序与旧版串行 for 循环完全一致（golden）", async () => {
    const order: string[] = [];
    const tasks = models.map((_, i) => task(`t${i}`, [], async () => { order.push(`t${i}`); }));
    await schedule(tasks, { concurrency: 1 });
    expect(order).toEqual(["t0", "t1", "t2", "t3", "t4"]);
  });

  it("⑦ DAG 的屏障节点覆盖全部模型（写安全前置）", () => {
    const dag = buildDag(models);
    const bar = dag.find((n) => n.id === "barrier-all-results")!;
    expect(bar.dependsOn).toHaveLength(5);
    expect(dag.filter((n) => n.id.startsWith("P2-IMPL:"))).toHaveLength(5);
    expect(dag.filter((n) => n.id.startsWith("P2-REVIEW:"))).toHaveLength(5);
  });
});
