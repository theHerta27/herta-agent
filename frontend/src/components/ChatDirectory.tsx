import { useEffect, useState } from 'react';
import type { WorkspaceRoot } from '../../shared/workspace-contracts';

const bridge = window.herta.workspace;

export function ChatDirectory({ disabled }: { disabled: boolean }) {
  const [roots, setRoots] = useState<WorkspaceRoot[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    if (disabled) return;
    let live = true;
    void bridge.roots().then(value => { if (live) setRoots(value); }).catch(() => {});
    return () => { live = false; };
  }, [disabled]);
  const choose = async () => {
    setBusy(true); setError('');
    try { const root = await bridge.chooseRoot(); if (root) await bridge.share(root.id, true); setRoots(await bridge.roots()); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  return <div className="chat-directory"><button disabled={disabled || busy} onClick={() => void choose()}>{busy ? '正在选择…' : '选择资料目录'}</button><span>{roots.some(root => root.shared) ? `聊天可读：${roots.filter(root => root.shared).map(root => root.label).join('、')}` : '尚未共享资料；选择后需确认允许聊天读取。'}</span>{error && <span className="error" role="alert">{error}</span>}</div>;
}
