import { describe, it, expect } from 'vitest';
import { TranscriptAdapter } from '../../apps/web/src/client/transcript.js';
const event = (type: string, extra: Record<string, any> = {}) => ({ type, taskId: 'P1', ts: 1, ...extra }) as any;
describe('SolveX to official Pi message components', () => {
  it('keeps parallel tasks and repeated turns separate', () => {
    const t = new TranscriptAdapter();
    for (const taskId of ['P1', 'P2']) t.apply(event('output', { taskId, state: 'delta', contentIndex: 0, delta: taskId }));
    t.apply(event('turn', { state: 'end' }));
    t.apply(event('turn', { state: 'start' }));
    t.apply(event('output', { state: 'delta', contentIndex: 0, delta: 'second' }));
    expect(t.get('P1').messages.filter(m => m.role === 'assistant').map((m: any) => m.content[0].text)).toEqual(['P1', 'second']);
    expect((t.get('P2').messages[0] as any).content[0].text).toBe('P2');
  });
  it('uses authoritative final content without duplicating streamed messages', () => {
    const t = new TranscriptAdapter();
    t.apply(event('output', { state: 'delta', contentIndex: 0, delta: 'partial' }));
    t.apply(event('output', { state: 'final', message: { role: 'assistant', content: [{ type: 'text', text: 'final' }] } }));
    expect(t.get('P1').messages).toHaveLength(1);
    expect((t.get('P1').messages[0] as any).content[0].text).toBe('final');
    t.apply(event('output', { state: 'delta', contentIndex: 0, delta: 'another' }));
    expect(t.get('P1').messages).toHaveLength(2);
  });
  it('pairs actual calls/results and does not mistake toolcall_end for execution completion', () => {
    const t = new TranscriptAdapter();
    t.apply(event('tool', { toolCallId: 't1', name: 'bash', state: 'start', args: { command: 'ls' } }));
    t.apply(event('tool', { toolCallId: 't1', name: 'bash', state: 'end', args: { command: 'ls' } }));
    expect(t.get('P1').pending.has('t1')).toBe(true);
    t.apply(event('tool', { toolCallId: 't1', name: 'bash', state: 'end', result: { content: [{ type: 'text', text: 'file.txt' }] } }));
    const state = t.get('P1');
    expect(state.pending.size).toBe(0);
    expect(state.messages.filter(m => m.role === 'toolResult')).toHaveLength(1);
    expect((state.messages.find(m => m.role === 'toolResult') as any).content[0].text).toBe('file.txt');
  });
  it('redacts private thinking and preserves a meaningful tool error', () => {
    const t = new TranscriptAdapter();
    t.apply(event('thinking', { state: 'delta', contentIndex: 0, delta: 'secret' }));
    t.apply(event('thinking', { state: 'end', contentIndex: 0, redacted: true }));
    expect(JSON.stringify(t.get('P1').messages)).not.toContain('secret');
    t.apply(event('tool', { toolCallId: 'x', name: 'python_execute', state: 'end', result: 'traceback', isError: true }));
    expect(t.get('P1').results.get('x')?.isError).toBe(true);
  });
  it('keeps final toolResult events out of assistant text and deduplicates them', () => {
    const t = new TranscriptAdapter();
    const message = { role: 'toolResult', toolCallId: 'x', toolName: 'read', content: [{ type: 'text', text: 'result' }], isError: false, timestamp: 1 };
    t.apply(event('output', { state: 'final', message }));
    t.apply(event('tool', { state: 'end', toolCallId: 'x', name: 'read', result: 'result' }));
    expect(t.get('P1').messages.filter(m => m.role === 'toolResult')).toHaveLength(1);
  });
  it('shows a placeholder for thinking omitted from the persisted event log', () => {
    const t = new TranscriptAdapter();
    t.apply(event('thinking', { state: 'start', contentIndex: 0 }));
    t.apply(event('thinking', { state: 'end', contentIndex: 0 }));
    expect((t.get('P1').messages[0] as any).content[0].thinking).toContain('未保存');
  });

});
