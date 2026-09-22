import type { ServiceEvent } from '../../shared/contracts';
import { applyToolEvent, type ToolActivity } from './tool-activity';
export interface LiveRun {
  id: string; sessionId: string; text: string; baseline: number; runId?: string; seq: number;
  phase: 'submitting' | 'running' | 'cancelling' | 'reconciling' | 'unknown' | 'done';
  partial: Record<string, string>; error?: string; gap?: boolean;
  tools: Record<string, ToolActivity>;
}
export function newRun(id: string, sessionId: string, text: string, baseline: number): LiveRun {
  return { id, sessionId, text, baseline, phase: 'submitting', partial: {}, tools: {}, seq: 0 };
}
export function reduceRun(previous: LiveRun, event: ServiceEvent): LiveRun {
  if (event.seq <= previous.seq || event.session_id !== previous.sessionId || (previous.runId && previous.runId !== event.run_id)) return previous;
  const run = { ...previous, runId: event.run_id, seq: event.seq, partial: { ...previous.partial }, gap: previous.gap || event.seq > previous.seq + 1 };
  const payload = event.payload;
  run.tools = applyToolEvent(run.tools, event);
  const id = String(payload.message_id ?? '');
  if (event.type === 'run.started' && run.phase === 'submitting') run.phase = 'running';
  if (event.type === 'llm.delta' && !['cancelling', 'reconciling', 'unknown', 'done'].includes(run.phase) && typeof payload.text === 'string') run.partial[id] = (run.partial[id] ?? '') + payload.text;
  if (event.type === 'llm.completed') {
    const message = payload.message as { content: string | null; tool_calls: unknown[] };
    if (message.tool_calls?.length) delete run.partial[id];
    else if (run.phase !== 'cancelling') run.partial[id] = message.content ?? '';
  }
  if (['run.completed', 'run.failed', 'run.cancelled', 'service.error'].includes(event.type)) {
    run.phase = 'reconciling';
    if (event.type !== 'run.completed') run.partial = {};
    if (event.type === 'service.error') run.error = '存储出现问题，尚不能确认本轮已保存。';
  }
  return run;
}
