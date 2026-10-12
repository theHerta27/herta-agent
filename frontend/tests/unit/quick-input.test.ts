import { expect, it, vi } from 'vitest';
import { ChatStore } from '../../src/state/chat-store';
import type { DesktopBridge } from '../../shared/contracts';
import { applyQuickInput } from '../../src/state/quick-input';

function fixture() {
  const startRun = vi.fn(async () => {});
  const bridge = { startRun, createSession: async () => ({ session_id: 'shared', created_at: '', updated_at: '' }), listSessions: async () => [], getSession: async (id: string) => ({ session: { session_id: id }, messages: [], current_run: null }) } as unknown as DesktopBridge;
  return { store: new ChatStore(bridge), startRun };
}
it('quick sends use the same ChatStore run reservation and never create a second agent', async () => {
  const { store, startRun } = fixture(); await store.connect({ state: 'ready' });
  await applyQuickInput(store, { kind: 'send', sessionId: null, expectedDraft: '', text: '来自快捷面板' });
  expect(store.state.selected).toBe('shared'); expect(startRun).toHaveBeenCalledTimes(1);
  await expect(applyQuickInput(store, { kind: 'send', sessionId: 'shared', expectedDraft: '', text: '重复提交' })).rejects.toThrow();
  expect(startRun).toHaveBeenCalledTimes(1);
});
it('stale quick input cannot overwrite another session or a changed main draft', async () => {
  const { store } = fixture(); await store.connect({ state: 'ready' }); store.setDraft('主窗口修改');
  await expect(applyQuickInput(store, { kind: 'draft', sessionId: null, expectedDraft: '', text: '旧草稿' })).rejects.toThrow();
  expect(store.view().draft).toBe('主窗口修改'); store.select('other');
  await expect(applyQuickInput(store, { kind: 'draft', sessionId: null, expectedDraft: '主窗口修改', text: '旧会话' })).rejects.toThrow();
  expect(store.view('draft').draft).toBe('主窗口修改');
});
