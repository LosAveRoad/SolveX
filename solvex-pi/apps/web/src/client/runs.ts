/** 前端「一个工作区 → 多个 run」的纯视图模型；不依赖 DOM，便于单测。 */

/** 是否贴近滚动容器底部；留阈值容忍消息高度变化与浮点误差。 */
export function isNearBottom(scrollTop: number, clientHeight: number,
                             scrollHeight: number, threshold = 48): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold;
}
export type RuntimeSummary = {
  model: string;
  thinking: string;
  concurrency: number;
  strict: boolean;
};
export type RunView = {
  id: string;
  status: string;
  created_at: string;
  problem?: string;
  workspaceId?: string;
  runtime?: RuntimeSummary | null;
};
export type WorkspaceView = {
  id: string;
  name: string;
  problemFilename?: string;
  files: { filename: string; size: number; problemReady: boolean }[];
  runs: RunView[];
};

/** 运行记录上的一行配置摘要；旧数据没有 runtime 时给出兜底文案。 */
export function runtimeLabel(run?: RunView | null): string {
  const r = run?.runtime;
  if (!r) return '默认配置';
  const parts = [r.model || '服务端默认'];
  if (r.thinking && r.thinking !== 'off') parts.push(`思考 ${r.thinking}`);
  parts.push(`并发 ${r.concurrency}`);
  if (r.strict) parts.push('严格');
  return parts.join(' · ');
}

/** 并行运行：当前选中的 run 在跑，也可以再开一次新运行。 */
export function canStartNewRun(workspace?: WorkspaceView | null, _selectedStatus?: string): boolean {
  return Boolean(workspace?.problemFilename);
}

export function hasActiveRuns(runs: readonly RunView[] = []): boolean {
  return runs.some((r) => r.status === 'running');
}

/** 轮询刷新列表时保留旧 run 的 runtime 摘要，不丢当前选中状态。 */
export function mergeRuns(current: readonly RunView[] = [], fresh: readonly RunView[] = []): RunView[] {
  const prev = new Map(current.map((r) => [r.id, r]));
  return fresh.map((r) => {
    const old = prev.get(r.id);
    return { ...old, ...r, runtime: r.runtime ?? old?.runtime ?? null };
  });
}

export function findRun(runs: readonly RunView[] = [], id?: string): RunView | undefined {
  return id ? runs.find((r) => r.id === id) : undefined;
}
