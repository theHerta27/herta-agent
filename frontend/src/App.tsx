import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { BackendStatus } from '../shared/contracts';
import { ChatStore } from './state/chat-store';
import { ConversationSidebar } from './components/ConversationSidebar';
import { WelcomeView } from './components/WelcomeView';
import { Composer } from './components/Composer';
import { MessageList } from './components/MessageList';
import { SettingsDialog } from './components/SettingsDialog';
import { CompanionRuntime } from './state/companion-runtime';
import { CompanionPanel } from './components/CompanionPanel';
import { VoiceInput } from './components/VoiceInput';
import { WorkspacePanel } from './components/WorkspacePanel';
import { ProductivityPanel } from './components/ProductivityPanel';
import { AudioControls, DailyContext } from './audio/context';
import './styles/companion.css';

const store = new ChatStore(window.herta);
const daily = new CompanionRuntime(window.herta.companion);

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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dailyOpen, setDailyOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [learningOpen, setLearningOpen] = useState(false);
  const spoken = useRef(new Set<string>());
  const [light, setLight] = useState(() => localStorage.getItem('herta-theme') === 'light');
  useEffect(() => { document.documentElement.dataset.theme = light ? 'light' : 'dark'; localStorage.setItem('herta-theme', light ? 'light' : 'dark'); }, [light]);
  useEffect(() => {
    if (status.state === 'ready' || status.state === 'needs_configuration') daily.start();
    else daily.stop();
    return () => daily.stop();
  }, [status.state]);
  useEffect(() => {
    if (filesOpen || learningOpen) return;
    for (const message of view.messages) {
      if (spoken.current.has(message.message_id)) continue;
      if (view.request?.runId === message.run_id && view.request.phase !== 'done') continue;
      spoken.current.add(message.message_id);
      if (view.request?.phase === 'done' && view.request.runId === message.run_id && message.message.role === 'assistant' && !message.message.tool_calls.length && daily.state.data?.preferences.auto_read && message.message.content) void daily.audio.read(message.message.content);
    }
  }, [view.messages, view.request?.phase, filesOpen, learningOpen]);
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

  return <DailyContext.Provider value={daily}><div className="app-shell">
    {settingsOpen && <SettingsDialog backend={status} busy={Object.values(state.views).some(value => store.isBusy(value))} onClose={() => setSettingsOpen(false)} />}
    {filesOpen && <WorkspacePanel onClose={() => setFilesOpen(false)} onDraft={text => { const draft = store.view().draft; store.setDraft(draft ? draft + '\n\n' + text : text); }} />}
    {learningOpen && <ProductivityPanel runtime={daily} sessionKey={state.selected ?? 'draft'} onClose={() => setLearningOpen(false)} onDraft={text => { const draft = store.view().draft; store.setDraft(draft ? draft + '\n\n' + text : text); }} />}
    <ConversationSidebar sessions={state.sessions.map(s => ({ ...s, active: store.isBusy(store.view(s.session_id)) }))} selected={state.selected} onSelect={id => store.select(id)} onNew={() => store.select(null)}
      collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} light={light} onTheme={() => setLight(!light)} />
    <main className="workspace">
      <header className="chat-header"><strong>{state.sessions.find(s => s.session_id === state.selected)?.title ?? '新对话'}</strong><div className="header-actions"><button disabled={!['ready', 'needs_configuration'].includes(status.state)} onClick={() => { void daily.audio.stopVoice(); setFilesOpen(true); }}>文件</button><button disabled={!['ready', 'needs_configuration'].includes(status.state)} onClick={() => { void daily.audio.stopVoice(); setLearningOpen(true); }}>学习</button><button onClick={() => setDailyOpen(!dailyOpen)} aria-expanded={dailyOpen}>日常</button><button onClick={() => setSettingsOpen(true)}>设置</button><span className="backend-status" role="status" aria-live="polite" data-state={status.state}>{labels[status.state]}</span></div></header>
      {status.state === 'needs_configuration' && <p className="notice">聊天模型未配置；历史仍可阅读。请打开设置填写模型连接，并通过启动环境配置密钥。</p>}
      {status.state === 'unavailable' && <p className="notice error">{status.reason === 'start_failed' ? 'Python 后端启动失败，请检查本地环境后重新打开应用。' : '后端连接不可用，请重新打开应用。'}</p>}
      {state.error && <p className="notice error">{state.error}<button onClick={() => void store.refresh()}>重试列表</button></p>}
      {view.error && <p className="notice error">{view.error}<button onClick={() => state.selected && void (view.request?.phase === 'unknown' ? store.reconcile(state.selected) : store.load(state.selected))}>{view.request?.phase === 'unknown' ? '核对状态' : '重试读取'}</button></p>}
      <div className="conversation" ref={scroll} onScroll={() => {
        const el = scroll.current!; following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        setShowLatest(!following.current); store.saveScroll(state.selected ?? 'draft', el.scrollTop);
      }}>
        {view.loading && <p className="content notice">正在读取会话…</p>}
        {!view.loading && view.messages.length === 0 && !busy ? <WelcomeView onExample={text => store.setDraft(text)} /> : <MessageList view={view} onRetryDiagnostics={() => state.selected && void store.load(state.selected)} />}
      </div>
      {showLatest && <button className="latest" onClick={() => { following.current = true; scroll.current!.scrollTop = scroll.current!.scrollHeight; }}>回到最新 ↓</button>}
      <div className="voice-row"><VoiceInput runtime={daily} disabled={filesOpen || learningOpen || busy || status.state !== 'ready'} sessionKey={state.selected ?? 'draft'} onText={text => { const draft = store.view().draft; store.setDraft(draft ? draft + '\n' + text : text); }} /><AudioControls /></div>
      <Composer value={view.draft} onChange={text => store.setDraft(text)} onSend={() => { void daily.audio.stopVoice(); void store.send(); }} onStop={() => { void daily.audio.stopVoice(); void store.stop(); }} busy={busy} cancelling={view.request?.phase === 'cancelling' || view.request?.phase === 'reconciling'} disabled={status.state !== 'ready' || view.loading || !view.loaded} />
    </main>
    {dailyOpen && <CompanionPanel runtime={daily} onClose={() => setDailyOpen(false)} />}
  </div></DailyContext.Provider>;
}
