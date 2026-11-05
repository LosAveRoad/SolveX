import type { DagNode } from "./dag.js";
import { ready } from "./dag.js";
import type { StageNode } from "../events/types.js";

export type SchedTask = DagNode & { run?: (signal?: AbortSignal) => Promise<void>; skip?: boolean };
export type SchedulerOptions = {
  concurrency: number;
  signal?: AbortSignal;
  onState?: (node: DagNode, state: StageNode["state"]) => void;
  onBarrier?: (id: string, state: "waiting" | "released", completed: number, total: number) => void;
};
export type ScheduleResult = {
  done: string[]; failed: string[]; skipped: string[]; aborted: boolean; peakActive: number;
};

/** 带并发上限的 Promise 池 + 屏障（T2.9 / D2）。零 Pi 依赖，FakeRunner 可完整驱动。
 *  - 屏障：依赖全部结算（done|failed|skipped）才 released，期间发 waiting(completed,total)
 *  - 失败隔离：单节点抛错只标 failed，不取消兄弟
 *  - 取消：abort 后不再派发新任务，在跑任务共享同一 signal
 */
export async function schedule(tasks: SchedTask[], opts: SchedulerOptions): Promise<ScheduleResult> {
  const done = new Set<string>(), failed = new Set<string>(), skipped = new Set<string>();
  const running = new Map<string, Promise<void>>();
  const limit = Math.max(1, Math.floor(opts.concurrency));
  let peakActive = 0, aborted = false;
  const settled = () => new Set<string>([...done, ...failed, ...skipped]);
  const allSettled = () => { const s = settled(); return tasks.every((t) => s.has(t.id)); };

  while (!allSettled()) {
    if (opts.signal?.aborted) { aborted = true; break; }
    const s = settled();

    // 显式跳过（resume / skipToWriting）
    for (const t of tasks) if (t.skip && !s.has(t.id)) {
      skipped.add(t.id); opts.onState?.(t, "skipped");
    }
    s.clear(); for (const x of settled()) s.add(x);

    // 屏障：依赖全部结算后释放
    for (const t of tasks) {
      if (t.kind !== "barrier" || s.has(t.id)) continue;
      const total = t.dependsOn.length;
      const completed = t.dependsOn.filter((d) => s.has(d)).length;
      if (completed === total) {
        opts.onBarrier?.(t.id, "released", completed, total);
        done.add(t.id); opts.onState?.(t, "done");
      } else {
        opts.onBarrier?.(t.id, "waiting", completed, total);
      }
    }
    s.clear(); for (const x of settled()) s.add(x);

    // 线性依赖：前置节点 failed 时阻断下游（strict 质量门靠此阻止 P4）。
    // 屏障例外：它本就是失败汇总点，依赖含 failed 仍会 released（失败隔离）。
    for (const t of tasks) {
      if (t.kind === "barrier" || t.skip || s.has(t.id)) continue;
      if (t.dependsOn.some((d) => failed.has(d))) {
        skipped.add(t.id); opts.onState?.(t, "skipped");
      }
    }
    s.clear(); for (const x of settled()) s.add(x);

    // 派发普通任务（并发上限）
    const candidates = ready(tasks, s, new Set<string>(), new Set(running.keys()))
      .filter((t) => t.kind !== "barrier" && !t.skip);
    for (const t of candidates) {
      if (running.size >= limit) break;
      if (opts.signal?.aborted) { aborted = true; break; }
      opts.onState?.(t, "running");
      const job = (async () => {
        try {
          if (t.run) await t.run(opts.signal);
          done.add(t.id); opts.onState?.(t, "done");
        } catch {
          failed.add(t.id); opts.onState?.(t, opts.signal?.aborted ? "aborted" : "failed");
        } finally { running.delete(t.id); }
      })();
      running.set(t.id, job);
      peakActive = Math.max(peakActive, running.size);
    }
    if (aborted) break;

    if (running.size === 0) {
      // 没有在跑任务且没有可派发任务 → 只剩未满足的屏障，或死锁
      const remaining = tasks.filter((t) => !settled().has(t.id));
      if (remaining.length === 0 || candidates.length === 0) break;
    }
    if (running.size) await Promise.race([...running.values()]);
  }

  return { done: [...done], failed: [...failed], skipped: [...skipped], aborted, peakActive };
}
