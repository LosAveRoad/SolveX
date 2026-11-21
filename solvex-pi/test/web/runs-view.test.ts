import { describe, it, expect } from 'vitest';
import { runtimeLabel, canStartNewRun, hasActiveRuns, mergeRuns, findRun, isNearBottom,
  type RunView, type WorkspaceView } from '../../apps/web/src/client/runs.js';

const run = (over: Partial<RunView> = {}): RunView => ({
  id: 'r1', status: 'completed', created_at: '2026-01-01T00:00:00.000Z',
  runtime: { model: 'openai/gpt-5', thinking: 'high', concurrency: 3, strict: false }, ...over,
});
const workspace = (runs: RunView[] = []): WorkspaceView =>
  ({ id: 'w1', name: 'A题', problemFilename: 'p.md', files: [], runs });

describe('生成时自动滚动判定', () => {
  it('贴近底部才自动跟随，用户上滚后暂停', () => {
    expect(isNearBottom(952, 400, 1400)).toBe(true);      // 距底 48，仍在阈值内
    expect(isNearBottom(900, 400, 1400)).toBe(false);     // 距底 100，已上滚
    expect(isNearBottom(1000, 400, 1400)).toBe(true);     // 已到底
    expect(isNearBottom(900, 400, 1400, 120)).toBe(true); // 自定义阈值
  });
});

describe('前端多 runtime 视图模型', () => {
  it('runtimeLabel 展示模型/思考/并发/严格，旧数据兜底', () => {
    expect(runtimeLabel(run())).toBe('openai/gpt-5 · 思考 high · 并发 3');
    expect(runtimeLabel(run({ runtime: { model: 'x/y', thinking: 'off', concurrency: 1, strict: true } })))
      .toBe('x/y · 并发 1 · 严格');
    expect(runtimeLabel(run({ runtime: null }))).toBe('默认配置');
    expect(runtimeLabel(undefined)).toBe('默认配置');
  });

  it('当前 run 在跑也允许新建运行；缺题目时禁用', () => {
    expect(canStartNewRun(workspace(), 'running')).toBe(true);
    expect(canStartNewRun(workspace([run({ status: 'running' })]), 'running')).toBe(true);
    expect(canStartNewRun({ ...workspace(), problemFilename: undefined })).toBe(false);
    expect(canStartNewRun(null)).toBe(false);
  });

  it('hasActiveRuns 只看列表本身，不看选中项', () => {
    expect(hasActiveRuns([run({ status: 'completed' }), run({ id: 'r2', status: 'running' })])).toBe(true);
    expect(hasActiveRuns([run()])).toBe(false);
    expect(hasActiveRuns()).toBe(false);
  });

  it('mergeRuns 用服务端状态覆盖、保留缺失的 runtime 摘要', () => {
    const current = [run({ status: 'running' })];
    const fresh = [{ id: 'r1', status: 'completed', created_at: '2026-01-01T00:00:00.000Z' }];
    const merged = mergeRuns(current, fresh);
    expect(merged[0].status).toBe('completed');
    expect(merged[0].runtime?.model).toBe('openai/gpt-5');
    expect(mergeRuns(current, [{ ...fresh[0], runtime: { model: 'a/b', thinking: 'off', concurrency: 1, strict: true } }])[0].runtime?.model).toBe('a/b');
  });

  it('findRun 按 runId 定位，切换 run 不会串到别的运行', () => {
    const runs = [run(), run({ id: 'r2', status: 'running' })];
    expect(findRun(runs, 'r2')?.status).toBe('running');
    expect(findRun(runs, 'nope')).toBeUndefined();
    expect(findRun(runs, undefined)).toBeUndefined();
  });
});
