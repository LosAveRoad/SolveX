// @ts-nocheck
// 说明：被测模块为浏览器原生 ESM .js（无 .d.ts）；本测试文件关闭类型检查，运行时由 vitest/esbuild 处理，避免污染 tsconfig 全量 typecheck。
import {
  orderStages, stageStateClass, isFailed, barrierLabel, barrierStateClass,
  groupByParent, taskDetail, buildTimeline,
} from "../../apps/web/public/modules/stages.js";
import { describe, it, expect } from "vitest";

const stages = {
  P4: { id: "P4", label: "写作", phase: 4, kind: "stage", state: "pending", dependsOn: [] },
  P1: { id: "P1", label: "建模", phase: 1, kind: "stage", state: "done", dependsOn: [] },
  P3: { id: "P3", label: "聚合", phase: 3, kind: "stage", state: "pending", dependsOn: [] },
  P2: { id: "P2", label: "实现", phase: 2, kind: "stage", state: "running", dependsOn: ["P1"] },
  m1: { id: "m1", label: "model_1", phase: 2, kind: "task", state: "done", parentId: "P2", dependsOn: [], taskId: "P2-IMPL:model_1" },
  m2: { id: "m2", label: "model_2", phase: 2, kind: "task", state: "failed", parentId: "P2", dependsOn: [], taskId: "P2-IMPL:model_2" },
  m3: { id: "m3", label: "model_3", phase: 2, kind: "task", state: "running", parentId: "P2", dependsOn: [], taskId: "P2-IMPL:model_3" },
};

describe("T5.19 stages 运行阶段 DAG 时间线", () => {
  it("orderStages 按 phase、id 稳定排序", () => {
    const arr = orderStages(stages);
    expect(arr[0].id).toBe("P1");
    expect(arr[arr.length - 1].id).toBe("P4");
    expect(arr.filter((n) => n.phase === 2)).toHaveLength(4);
    expect(stages.P4.state).toBe("pending"); // 输入未被修改
  });

  it("stageStateClass / isFailed：失败标红", () => {
    expect(stageStateClass({ state: "running" })).toBe("is-running");
    expect(stageStateClass({ state: "done" })).toBe("is-done");
    expect(stageStateClass({ state: "failed" })).toBe("is-failed");
    expect(isFailed(stages.m2)).toBe(true);
    expect(isFailed(stages.m1)).toBe(false);
  });

  it("barrierLabel 显示 3/5，released 状态类正确", () => {
    expect(barrierLabel({ completed: 3, total: 5 })).toBe("3/5");
    expect(barrierLabel({ completed: 0, total: 0 })).toBe("0/0");
    expect(barrierStateClass({ state: "waiting" })).toBe("is-waiting");
    expect(barrierStateClass({ state: "released" })).toBe("is-done");
  });

  it("groupByParent：并行节点独立挂在 P2 下", () => {
    const roots = groupByParent(stages);
    const p2 = roots.find((r) => r.node.id === "P2");
    expect(p2).toBeTruthy();
    expect(p2.children).toHaveLength(3);           // 3 个并行子节点
    expect(p2.children.map((c) => c.node.state)).toEqual(["done", "failed", "running"]); // 状态独立
    const p1 = roots.find((r) => r.node.id === "P1");
    expect(p1.children).toHaveLength(0);
  });

  it("taskDetail 展开可见 turn / 工具 / 思考 / 输出", () => {
    const tasks = {
      "P2-IMPL:model_1": {
        turns: [{ state: "start", turn: 1 }, { state: "end", turn: 1 }],
        tools: { t1: { name: "python" }, t2: { name: "write" } },
        thinkingBlocks: { 0: { content: "想" } },
        output: { 0: { content: "结果" } },
      },
    };
    const d = taskDetail(stages.m1, tasks);
    expect(d.counts).toEqual({ turns: 2, tools: 2, thinking: 1, output: 1 });
    expect(d.turns).toHaveLength(2);
    expect(d.tools.map((t) => t.name)).toEqual(["python", "write"]);
    expect(d.thinkingBlocks[0].content).toBe("想");
    expect(d.outputBlocks[0].content).toBe("结果");
    // 无对应 task 时返回空明细
    expect(taskDetail({ id: "unknown" }, tasks).counts).toEqual({ turns: 0, tools: 0, thinking: 0, output: 0 });
  });

  it("buildTimeline 输出阶段行 + 屏障行", () => {
    const rows = buildTimeline(stages, {
      "all-results": { id: "all-results", state: "waiting", completed: 3, total: 5 },
    });
    expect(rows.some((r) => r.kind === "barrier" && barrierLabel(r.barrier) === "3/5")).toBe(true);
    const p2row = rows.find((r) => r.kind === "node" && r.node.id === "P2");
    expect(p2row.children).toHaveLength(3);
    expect(buildTimeline({}, {})).toEqual([]);
  });
});
