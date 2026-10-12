import { useEffect, useRef, useState } from 'react';
import type { QuickState, QuickWindowBridge } from '../../shared/quick-contracts';
import '../styles/quick.css';

const bridge = (window as unknown as { hertaQuick: QuickWindowBridge }).hertaQuick;
export function QuickPanel() {
  const [state, setState] = useState<QuickState | null>(null); const [text, setText] = useState(''); const [dirty, setDirty] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const initial = useRef<QuickState | null>(null); const editing = useRef(false);
  useEffect(() => { let live = true; const update = (value: QuickState | null) => { if (!live) return; setState(value); if (value && !editing.current) { initial.current = value; setText(value.draft); } }; void bridge.state().then(update); const unsubscribe = bridge.onState(update); return () => { live = false; unsubscribe(); }; }, []);
  async function submit(kind: 'draft' | 'send') {
    if (!initial.current) return; setBusy(true); setError('');
    try { await bridge.input({ kind, sessionId: initial.current.sessionId, expectedDraft: initial.current.draft, text }); editing.current = false; setDirty(false); const next = await bridge.state(); setState(next); initial.current = next; setText(next?.draft ?? ''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败，请打开主窗口检查。'); }
    finally { setBusy(false); }
  }
  return <main className="quick-panel"><header><div><strong>Herta</strong><span>{state?.title ?? '正在连接主窗口…'}</span></div><button onClick={() => void bridge.close()} aria-label="关闭快捷面板">×</button></header><p className="quick-status">{state?.busy ? '当前对话处理中' : state?.ready ? '与主窗口共用当前对话' : '打开主窗口完成配置'}</p>{state?.lastReply && <blockquote>{state.lastReply}</blockquote>}<textarea aria-label="快捷消息" autoFocus maxLength={10000} value={text} placeholder="有什么想问黑塔的？" onChange={e => { editing.current = true; setDirty(true); setText(e.target.value); }} />{error && <p role="alert">{error}</p>}<footer><button disabled={busy || !state || !dirty} onClick={() => void submit('draft')}>保存到主窗口草稿</button><button disabled={busy || !state?.ready || state.busy || !text.trim()} onClick={() => void submit('send')}>发送</button><button onClick={() => void bridge.showMain()}>主窗口</button>{dirty && <button disabled={busy} onClick={() => { editing.current = false; setDirty(false); initial.current = state; setText(state?.draft ?? ''); setError(''); }}>丢弃本地修改并同步</button>}</footer></main>;
}
