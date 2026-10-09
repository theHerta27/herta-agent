import { expect, it } from 'vitest';
import { newRun, reduceRun } from '../../src/state/run-reducer';
import type { ServiceEvent } from '../../shared/contracts';

const event = (seq: number, type: string, payload: Record<string, unknown> = {}): ServiceEvent => ({ seq, type, payload, session_id: 's', run_id: 'r', schema_version: 1, timestamp: '' });
it('deduplicates deltas and replaces partial with the validated full message', () => {
  let run = newRun('q', 's', 'question', 0);
  run = reduceRun(run, event(1, 'llm.delta', { message_id: 'm', text: '半' }));
  run = reduceRun(run, event(1, 'llm.delta', { message_id: 'm', text: '半' }));
  expect(run.partial.m).toBe('半');
  run = reduceRun(run, event(2, 'llm.completed', { message_id: 'm', message: { role: 'assistant', content: '完整', tool_calls: [] } }));
  expect(run.partial.m).toBe('完整');
});
it('drops cancelled partial and ignores late deltas; service.error never implies persistence', () => {
  let run = newRun('q', 's', 'question', 0);
  run = reduceRun(run, event(1, 'llm.delta', { message_id: 'm', text: '半' }));
  run.phase = 'cancelling';
  run = reduceRun(run, event(2, 'llm.delta', { message_id: 'm', text: '迟到' }));
  expect(run.partial.m).toBe('半');
  run = reduceRun(run, event(3, 'run.cancelled'));
  expect(run.partial).toEqual({});
  run = reduceRun(run, event(4, 'service.error', { persisted: false }));
  expect(run.phase).toBe('reconciling');
  expect(run.error).toBeTruthy();
});

it('keeps context diagnostics from SSE across terminal reconciliation and ignores duplicate events', () => {
  const context = { step: 1, policy_version: 'v1', persona_hash: 'hash', estimated_input_tokens: 700, input_budget: 1000, tool_schema_tokens: 100, retained_message_indices: [0, 3], omitted_message_count: 2, summary_refs: [], evidence_refs: ['chunk-1'], reason: 'recent_window' };
  let run = newRun('q', 's', 'question', 0);
  run = reduceRun(run, event(1, 'context.prepared', context));
  run = reduceRun(run, event(1, 'context.prepared', context));
  run = reduceRun(run, event(2, 'run.completed'));
  expect(run.contexts).toEqual([context]);
});
