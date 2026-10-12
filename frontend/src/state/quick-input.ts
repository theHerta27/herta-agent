import type { ChatStore } from './chat-store';
import type { QuickInput } from '../../shared/quick-contracts';

export async function applyQuickInput(store: ChatStore, input: QuickInput) {
  if (!input || !['draft', 'send'].includes(input.kind) || typeof input.text !== 'string' || input.text.length > 10000 || input.text.includes('\0') || input.sessionId !== store.state.selected || input.expectedDraft !== store.view().draft) throw new Error('当前会话或草稿已变化，请刷新快捷面板后重试。');
  if (input.kind === 'send' && (store.isBusy() || store.state.backend.state !== 'ready' || !store.view().loaded || store.view().loading || !input.text.trim())) throw new Error('当前对话无法发送，请等待本轮完成。');
  store.setDraft(input.text);
  if (input.kind === 'send') await store.send();
}
