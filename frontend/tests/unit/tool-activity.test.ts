import { expect, it } from 'vitest';
import { projectTools } from '../../src/state/tool-activity';
import { newRun, reduceRun } from '../../src/state/run-reducer';
import type { MessageRecord, ServiceEvent } from '../../shared/contracts';

it('keeps reused call IDs separate across steps and reconstructs saved RAG sources', () => {
  const records = [1, 2].flatMap(step => [
    { run_id: 'r', step, message: { role: 'assistant', tool_calls: [{ id: 'same', name: 'search_knowledge', arguments: '{"query":"黑塔"}' }] } },
    { run_id: 'r', step, message: { role: 'tool', tool_call_id: 'same', content: JSON.stringify({ ok: true, data: { query: '黑塔', chunks: [{ id: 'c' + step, source: '角色资料.md', score: 0.8 }] } }) } },
  ]) as unknown as MessageRecord[];
  const tools = projectTools(records);
  expect(tools).toHaveLength(2);
  expect(tools[0].chunks?.[0].id).toBe('c1');
  expect(tools[1].chunks?.[0].id).toBe('c2');
});

it('shows failure without started, and merges rag.retrieved into the same activity', () => {
  const event = (seq: number, type: string, payload: Record<string, unknown>): ServiceEvent => ({ seq, type, payload, run_id: 'r', session_id: 's', schema_version: 1, timestamp: '' });
  let run = newRun('q', 's', 'x', 0);
  run = reduceRun(run, event(1, 'tool.failed', { step: 1, tool_call_id: 'a', name: 'echo', result: { ok: false, error: { message: '参数无效' } } }));
  expect(Object.values(run.tools)[0].state).toBe('failed');
  run = reduceRun(run, event(2, 'tool.completed', { step: 2, tool_call_id: 'a', name: 'search_knowledge', result: { ok: true, data: { chunks: [] } } }));
  run = reduceRun(run, event(3, 'rag.retrieved', { step: 2, tool_call_id: 'a', query: '黑塔', chunks: [{ id: 'c', source: '资料.md', score: 0.9 }] }));
  expect(Object.values(run.tools)).toHaveLength(2);
  expect(Object.values(run.tools)[1].chunks).toHaveLength(1);
});
