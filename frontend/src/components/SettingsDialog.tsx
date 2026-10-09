import { useEffect, useRef, useState } from 'react';
import type { BackendStatus, PublicSettings } from '../../shared/contracts';

export function SettingsDialog({ busy, backend, onClose }: { busy: boolean; backend: BackendStatus; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [settings, setSettings] = useState<PublicSettings>();
  const [applying, setApplying] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
    let live = true;
    window.herta.getSettings().then(value => { if (live) setSettings(value); }).catch(() => { if (live) { setError(true); setMessage('设置读取失败，请关闭后重试。'); } });
    return () => { live = false; };
  }, []);
  const update = <K extends keyof PublicSettings>(key: K, value: PublicSettings[K]) => { setSettings(previous => previous && { ...previous, [key]: value }); setMessage(''); };
  const apply = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!settings || busy || applying) return;
    setApplying(true); setError(false); setMessage('正在应用设置并重启服务…');
    try {
      const result = await window.herta.applySettings(settings);
      setSettings(result.settings);
      const ready = result.backend.state === 'ready';
      setError(!ready);
      setMessage(ready ? '设置已应用。' : '设置已保存，但聊天配置未就绪。请检查模型连接和启动环境中的密钥。');
    }
    catch (cause) {
      setError(true);
      const code = String(cause);
      setMessage(code.includes('runs_active') ? '请等待所有运行结束或停止运行后，再应用设置。'
        : code.includes('invalid_settings') ? '请检查 Base URL 和预算；输出预留需小于窗口减 256。'
        : code.includes('settings_restart_failed') ? '服务启动失败，已恢复原设置。请检查本地环境后重试。'
        : code.includes('settings_recovery_failed') ? '服务启动失败，原设置已保留，但服务恢复失败。请检查本地环境后重新打开应用。'
        : code.includes('settings_write_failed') ? '设置保存失败，服务已按原设置重新启动。'
        : '设置未能应用，请等待服务就绪后重试。');
      if (['settings_restart_failed', 'settings_recovery_failed', 'settings_write_failed'].some(value => code.includes(value))) {
        try { setSettings(await window.herta.getSettings()); } catch { /* Preserve the displayed draft if the public config cannot be read. */ }
      }
    } finally { setApplying(false); }
  };
  return <dialog className="settings-dialog" ref={dialog} aria-labelledby="settings-title" onCancel={event => { if (applying) event.preventDefault(); else onClose(); }}>
    <form onSubmit={event => void apply(event)}>
      <header><h2 id="settings-title">设置</h2><button type="button" aria-label="关闭设置" onClick={onClose} disabled={applying}>×</button></header>
      <p className="settings-note">密钥仅从启动环境读取，不会在界面显示或保存。</p>
      {backend.embeddingProvider && <p className="settings-service"><strong>{backend.embeddingProvider === 'local' ? '本地 Embedding' : 'Embedding'} · {backend.ragAvailable ? '检索已就绪' : '检索未就绪'}</strong><br />{backend.embeddingModel || '未指定模型'}{backend.embeddingProvider === 'local' && <><br />本地模型在电脑上运行，无需 API Key 或 Base URL。</>}</p>}
      {backend.mcpAvailable && <p className="settings-note">只读 MCP 工具已连接。</p>}
      {backend.mcpError && <p className="settings-note error">MCP 连接不可用：{backend.mcpError}</p>}
      {!settings ? <p>正在读取设置…</p> : <fieldset disabled={applying}>
        <legend>模型连接</legend>
        <label>聊天 Base URL<input type="url" value={settings.chatBaseUrl} placeholder="https://api.example.com/v1" onChange={event => update('chatBaseUrl', event.target.value)} /></label>
        <label>聊天模型<input value={settings.chatModel} maxLength={512} onChange={event => update('chatModel', event.target.value)} /></label>
        <label>Embedding 运行方式<select value={settings.embeddingProvider} onChange={event => update('embeddingProvider', event.target.value as PublicSettings['embeddingProvider'])}><option value="auto">自动选择</option><option value="local">本地模型</option><option value="remote">远程 API</option></select></label>
        {settings.embeddingProvider !== 'local' && <><label>Embedding Base URL<input type="url" value={settings.embeddingBaseUrl} required={settings.embeddingProvider === 'remote'} placeholder="https://api.example.com/v1" onChange={event => update('embeddingBaseUrl', event.target.value)} /></label>
        <label>Embedding 模型<input value={settings.embeddingModel} required={settings.embeddingProvider === 'remote'} maxLength={512} onChange={event => update('embeddingModel', event.target.value)} /></label></>}
        {settings.embeddingProvider === 'local' && <p className="settings-note">使用本机已缓存的模型，无需填写远程连接。模型路径可通过启动环境指定。</p>}
        <div className="settings-section">上下文预算</div>
        <div className="settings-budgets">
          <label>上下文窗口<input type="number" min={512} max={2000000} step={1} required value={settings.contextWindow} onChange={event => update('contextWindow', Number(event.target.value))} /></label>
          <label>输出预留<input type="number" min={64} max={settings.contextWindow - 257} step={1} required value={settings.outputReserve} onChange={event => update('outputReserve', Number(event.target.value))} /></label>
        </div>
        <p className="settings-note">按模型实际窗口填写 Token 数；输入还会预留工具定义所需空间。</p>
        <label className="settings-checkbox"><input type="checkbox" checked={settings.summaryEnabled} onChange={event => update('summaryEnabled', event.target.checked)} />启用旧历史摘要</label>
      </fieldset>}
      {busy && <p className="settings-note">请等待所有运行结束或停止运行后，再应用设置。</p>}
      {message && <p className={error ? 'error' : 'settings-result'} aria-live="polite">{message}</p>}
      <footer><span>应用设置会重启服务，会话历史保留。</span><button type="submit" className="settings-apply" disabled={!settings || busy || applying}>{applying ? '正在应用…' : '保存并应用'}</button></footer>
    </form>
  </dialog>;
}