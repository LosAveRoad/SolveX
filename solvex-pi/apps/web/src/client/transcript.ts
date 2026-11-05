import type { AgentMessage } from '@earendil-works/pi-agent-core';
import type { AssistantMessage, ToolResultMessage, TextContent, ImageContent } from '@earendil-works/pi-ai';
import type { SolveXEvent } from '@solvex/core';

type TaskTranscript = { messages: AgentMessage[]; pending: Set<string>;
  results: Map<string, ToolResultMessage>; active?: AssistantMessage };
const zeroUsage = () => ({ input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
  totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } });
function resultContent(value: unknown): (TextContent | ImageContent)[] {
  const v = value as any;
  if (Array.isArray(v?.content)) return v.content;
  return [{ type: 'text', text: typeof v === 'string' ? v : JSON.stringify(v ?? '') }];
}

/** Adapts transport events only; no Agent, prompts, credentials or tools run in the browser. */
export class TranscriptAdapter {
  private tasks = new Map<string, TaskTranscript>();
  get(id: string): TaskTranscript {
    if (!this.tasks.has(id)) this.tasks.set(id, { messages: [], pending: new Set(), results: new Map() });
    return this.tasks.get(id)!;
  }
  private assistant(t: TaskTranscript, ts: number) {
    if (!t.active) {
      t.active = { role: 'assistant', content: [], api: 'openai-completions', provider: 'solvex',
        model: 'pipeline', usage: zeroUsage(), stopReason: 'stop', timestamp: ts };
      t.messages.push(t.active);
    }
    return t.active;
  }
  private result(t: TaskTranscript, result: ToolResultMessage) {
    const index = t.messages.findIndex(m => m.role === 'toolResult' && m.toolCallId === result.toolCallId);
    if (index < 0) t.messages.push(result); else t.messages[index] = result;
    t.results.set(result.toolCallId, result); t.pending.delete(result.toolCallId);
  }
  apply(e: SolveXEvent) {
    if (!('taskId' in e) || !e.taskId) return;
    const t = this.get(e.taskId); const ts = e.ts ?? Date.now();
    if (e.type === 'turn') { t.active = undefined; return; }
    if (e.type === 'output' && e.state === 'final') {
      const raw = e.message as any;
      if (raw?.role === 'toolResult') { this.result(t, raw); return; }
      if (raw?.role !== 'assistant') return;
      const a = this.assistant(t, ts);
      Object.assign(a, raw, { usage: raw.usage ?? a.usage });
      t.active = undefined; return;
    }
    if (e.type === 'thinking' || e.type === 'output') {
      const a = this.assistant(t, ts); const i = e.contentIndex;
      while (a.content.length <= i) a.content.push({type:'text',text:''});
      if (e.type === 'thinking') {
        const prior = a.content[i];
        const prev = prior?.type === 'thinking' ? prior.thinking : '';
        a.content[i] = { type: 'thinking', thinking: e.redacted ? '思考内容未保存或已隐藏' :
          e.state === 'start' ? '' : e.state === 'end' ? e.content ?? (prev || '思考内容未保存或已隐藏') : (prev + (e.delta ?? '')).slice(0, 65536) };
      } else {
        const prior = a.content[i]; const prev = prior?.type === 'text' ? prior.text : '';
        a.content[i] = { type: 'text', text: e.state === 'end' ? e.content ?? prev : (prev + (e.delta ?? '')).slice(0, 65536) };
      }
    }
    if (e.type === 'tool') {
      if (e.toolCallId.startsWith('ci:') && !e.name) return; // partial tool-call JSON, not an execution
      const callId = e.toolCallId;
      let call = t.messages.flatMap(m => m.role === 'assistant' ? m.content : [])
        .find(c => c?.type === 'toolCall' && c.id === callId);
      if (!call) {
        const a = this.assistant(t, ts);
        call = { type: 'toolCall', id: callId, name: e.name || 'tool', arguments: (e.args ?? {}) as any };
        a.content.push(call);
      } else if (call.type === 'toolCall') {
        if (e.name) call.name = e.name;
        if (e.args) call.arguments = e.args as any;
      }
      if (e.state === 'end' && e.result !== undefined) {
        this.result(t, { role: 'toolResult', toolCallId: callId, toolName: e.name,
          content: resultContent(e.result), isError: !!e.isError, timestamp: ts });
      } else if (e.state === 'update' && e.partialResult !== undefined) {
        this.result(t, { role: 'toolResult', toolCallId: callId, toolName: e.name,
          content: resultContent(e.partialResult), isError: false, timestamp: ts });
        t.pending.add(callId);
      } else if (!t.results.has(callId)) t.pending.add(callId);
    }
    // Lit property updates use array identity; never hand components an old array.
    t.messages = [...t.messages];
  }
}
