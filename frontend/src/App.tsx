import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { BackendStatus } from '../shared/contracts';
import { ChatStore } from './state/chat-store';
import { ConversationSidebar } from './components/ConversationSidebar';
import { WelcomeView } from './components/WelcomeView';
import { Composer } from './components/Composer';
import { MessageList } from './components/MessageList';

const store = new ChatStore(window.herta);

const labels: Record<BackendStatus['state'], string> = {
  starting: '正在启动', ready: '服务就绪', needs_configuration: '配置未就绪',
  unavailable: '后端不可用', stopping: '正在退出', stopped: '服务已停止',
};

export function App() {
  const state = useSyncExternalStore(store.subscribe, store.snapshot);
  const status = state.backend;
  const view = store.view();
  const busy = store.isBusy(view);
  const scroll = useRef<HTMLDivElement>(null);
  const previous = useRef<string | null>(null);
  const following = useRef(true);
  const [showLatest, setShowLatest] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [light, setLight] = useState(() => localStorage.getItem('herta-theme') === 'light');
  useEffect(() => { document.documentElement.dataset.theme = light ? 'light' : 'dark'; localStorage.setItem('herta-theme', light ? 'light' : 'dark'); }, [light]);
  useLayoutEffect(() => {
    const element = scroll.current;
    if (!element) return;
    if (previous.current !== state.selected) {
      previous.current = state.selected;
      element.scrollTop = view.scrollTop ?? element.scrollHeight;
      following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
    } else if (following.current) element.scrollTop = element.scrollHeight;
  });
  useEffect(() => {
    let live = true;
    let notified = false;
    const stopEvents = window.herta.onRunEvents(store.onPacket);
    const unsubscribe = window.herta.onBackendStatus(value => {
      notified = true;
      void store.connect(value);
    });
    window.herta.getBackendStatus().then(value => {
      if (live && !notified) void store.connect(value);
    }).catch(() => { if (live) void store.connect({ state: 'unavailable' }); });
    return () => { live = false; unsubscribe(); stopEvents(); };
  }, []);

  return <div className="app-shell">
    <ConversationSidebar sessions={state.sessions.map(s => ({ ...s, active: store.isBusy(store.view(s.session_id)) }))} selected={state.selected} onSelect={id => store.select(id)} onNew={() => store.select(null)}
      collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} light={light} onTheme={() => setLight(!light)} />
    <main className="workspace">
      <header className="chat-header"><strong>{state.sessions.find(s => s.session_id === state.selected)?.title ?? '新对话'}</strong><span className="backend-status" role="status" aria-live="polite" data-state={status.state}>{labels[status.state]}</span></header>
      {status.state === 'needs_configuration' && <p className="notice">聊天模型未配置；历史仍可阅读。请设置启动环境后重新打开应用。</p>}
      {status.state === 'unavailable' && <p className="notice error">{status.reason === 'start_failed' ? 'Python 后端启动失败，请检查本地环境后重新打开应用。' : '后端连接不可用，请重新打开应用。'}</p>}
      {state.error && <p className="notice error">{state.error}<button onClick={() => void store.refresh()}>重试列表</button></p>}
      {view.error && <p className="notice error">{view.error}<button onClick={() => state.selected && void (view.request?.phase === 'unknown' ? store.reconcile(state.selected) : store.load(state.selected))}>{view.request?.phase === 'unknown' ? '核对状态' : '重试读取'}</button></p>}
      <div className="conversation" ref={scroll} onScroll={() => {
        const el = scroll.current!; following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        setShowLatest(!following.current); store.saveScroll(state.selected ?? 'draft', el.scrollTop);
      }}>
        {view.loading && <p className="content notice">正在读取会话…</p>}
        {!view.loading && view.messages.length === 0 && !busy ? <WelcomeView onExample={text => store.setDraft(text)} /> : <MessageList view={view} />}
      </div>
      {showLatest && <button className="latest" onClick={() => { following.current = true; scroll.current!.scrollTop = scroll.current!.scrollHeight; }}>回到最新 ↓</button>}
      <Composer value={view.draft} onChange={text => store.setDraft(text)} onSend={() => void store.send()} onStop={() => void store.stop()} busy={busy} cancelling={view.request?.phase === 'cancelling' || view.request?.phase === 'reconciling'} disabled={status.state !== 'ready' || view.loading || !view.loaded} />
    </main>
  </div>;
}
