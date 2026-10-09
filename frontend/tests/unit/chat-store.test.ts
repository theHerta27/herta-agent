import { expect, it, vi } from 'vitest';
import { ChatStore } from '../../src/state/chat-store';
import type { DesktopBridge, SessionRecord } from '../../shared/contracts';

it('reserves one send before session creation; switching does not redirect the pending send', async () => {
  let created!: (session: SessionRecord) => void;
  const startRun = vi.fn(async () => {});
  const bridge = {
    createSession: () => new Promise<SessionRecord>(resolve => { created = resolve; }), startRun,
    getSession: async (id: string) => ({ session: { session_id: id }, messages: [], current_run: null }),
    getRun: vi.fn(), listSessions: async () => [],
  } as unknown as DesktopBridge;
  const store = new ChatStore(bridge);
  await store.connect({ state: 'ready' });
  store.setDraft('first');
  const sending = store.send();
  void store.send();
  store.select('other');
  created({ session_id: 'created', created_at: '', updated_at: '' });
  await sending;
  expect(startRun).toHaveBeenCalledTimes(1);
  expect(startRun.mock.calls[0]).toEqual([expect.objectContaining({ sessionId: 'created', text: 'first' })]);
  expect(store.state.selected).toBe('other');
});

it('slow history from A cannot replace selected B, and drafts survive navigation', async () => {
  const bridge = {
    getSession: async (id: string) => { if (id === 'a') await new Promise(resolve => setTimeout(resolve, 20)); return { messages: [], current_run: null }; },
  } as unknown as DesktopBridge;
  const store = new ChatStore(bridge);
  store.select('a'); store.setDraft('draft A'); store.select('b');
  await new Promise(resolve => setTimeout(resolve, 30));
  expect(store.state.selected).toBe('b'); expect(store.view('a').draft).toBe('draft A');
});

it('reloads persisted context diagnostics and keeps history readable when diagnostics are unavailable', async () => {
  let available = true;
  const context = { step: 1, policy_version: 'v1', persona_hash: 'hash', estimated_input_tokens: 700, input_budget: 1000, tool_schema_tokens: 100, retained_message_indices: [0], omitted_message_count: 0, summary_refs: [], evidence_refs: [], reason: 'full_history' };
  const bridge = {
    getSession: async () => ({ messages: [{ message_id: 'm', run_id: 'r', seq: 1, message: { role: 'user', content: 'saved', tool_calls: [] } }], current_run: null }),
    getRun: async () => ({ run: { run_id: 'r', status: 'completed' } }),
    getRunDiagnostics: async () => { if (!available) throw new Error('http_503'); return { contexts: [context], tools: [] }; },
  } as unknown as DesktopBridge;
  const first = new ChatStore(bridge);
  expect(await first.load('s')).toBe(true);
  expect(first.view('s').diagnostics.r.contexts).toEqual([context]);
  available = false;
  const reopened = new ChatStore(bridge);
  expect(await reopened.load('s')).toBe(true);
  expect(reopened.view('s').messages[0].message.content).toBe('saved');
  expect(reopened.view('s').diagnosticsErrors.r).toBeTruthy();
});

it('retries failed terminal diagnostics even when an earlier active snapshot remains cached', async () => {
  let terminal = false;
  let failing = false;
  const first = { step: 1, policy_version: 'v1', persona_hash: 'hash', estimated_input_tokens: 700, input_budget: 1000, tool_schema_tokens: 100, retained_message_indices: [0], omitted_message_count: 0, summary_refs: [], evidence_refs: [], reason: 'full_history' };
  const second = { ...first, step: 2 };
  const bridge = {
    getSession: async () => ({ messages: [{ message_id: 'm', run_id: 'r', seq: 1, message: { role: 'user', content: 'saved', tool_calls: [] } }], current_run: null }),
    getRun: async () => ({ run: { run_id: 'r', status: terminal ? 'completed' : 'running' } }),
    getRunDiagnostics: async () => { if (failing) throw new Error('http_503'); return { contexts: terminal ? [first, second] : [first], tools: [] }; },
  } as unknown as DesktopBridge;
  const store = new ChatStore(bridge);
  await store.load('s');
  expect(store.view('s').diagnostics.r.contexts).toHaveLength(1);
  terminal = true; failing = true;
  await store.load('s');
  expect(store.view('s').runs.r.status).toBe('completed');
  expect(store.view('s').diagnosticsErrors.r).toBeTruthy();
  failing = false;
  await store.load('s');
  expect(store.view('s').diagnostics.r.contexts).toEqual([first, second]);
  expect(store.view('s').diagnosticsErrors.r).toBeUndefined();
});
