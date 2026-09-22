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
