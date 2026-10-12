import { useEffect, useRef, useState } from 'react';
import '../styles/sharing.css';

export function MCPPanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null); const [text, setText] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  useEffect(() => { dialog.current?.showModal(); let live = true; void window.herta.mcp.get().then(value => { if (live) setText(JSON.stringify(value, null, 2)); }).catch(() => { if (live) setMessage('读取MCP配置失败，请核对本机配置。'); }); return () => { live = false; }; }, []);
  async function applyText() {
    setBusy(true); setMessage('正在验证并重启服务…');
    try { const result = await window.herta.mcp.apply(JSON.parse(text)); setMessage(result.saved ? result.available ? '配置已保存，只读工具已连接。' : '配置已保存，聊天配置就绪后可连接。' : '已取消，配置未保存。'); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  return <dialog className="sharing-dialog" ref={dialog} aria-labelledby="mcp-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}><header><h2 id="mcp-title">只读 MCP 扩展</h2><button disabled={busy} onClick={onClose}>关闭扩展设置</button></header><p>最多3个本机stdio服务。每项指定name、command（现有程序绝对路径）、args、allowed_tools和timeout（秒）。启动前原生确认；服务还必须声明工具只读。程序以当前用户权限运行，工具注解不提供系统隔离。请勿在参数中填写密钥。</p><details><summary>配置示例</summary><pre>{'{ "servers": [{ "name": "local", "command": "C:/path/to/python.exe", "args": ["C:/path/to/server.py"], "allowed_tools": ["read_status"], "timeout": 10 }] }'}</pre></details><textarea aria-label="MCP配置" rows={14} maxLength={32000} value={text} onChange={e => setText(e.target.value)} style={{ width: '100%' }} />{message && <p role="status">{message}</p>}<footer><button disabled={busy || !text} onClick={() => void applyText()}>应用扩展</button><button disabled={busy} onClick={() => { setBusy(true); void window.herta.mcp.apply({ servers: [] }).then(result => { if (result.saved) { setText('{"servers": []}'); setMessage('扩展已停用。'); } }).catch(e => setMessage(String(e))).finally(() => setBusy(false)); }}>停用全部扩展</button></footer></dialog>;
}
