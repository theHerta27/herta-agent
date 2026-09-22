import { useEffect, useState } from 'react';
import type { BackendStatus } from '../shared/contracts';

const labels: Record<BackendStatus['state'], string> = {
  starting: '正在启动', ready: '服务就绪', needs_configuration: '配置未就绪',
  unavailable: '后端不可用', stopping: '正在退出', stopped: '服务已停止',
};

export function App() {
  const [status, setStatus] = useState<BackendStatus>({ state: 'starting' });
  useEffect(() => {
    let live = true;
    let notified = false;
    const unsubscribe = window.herta.onBackendStatus(value => {
      notified = true;
      setStatus(value);
    });
    window.herta.getBackendStatus().then(value => {
      if (live && !notified) setStatus(value);
    }).catch(() => { if (live) setStatus({ state: 'unavailable' }); });
    return () => { live = false; unsubscribe(); };
  }, []);

  return <main>
    <header><h1>Herta</h1><span role="status" aria-live="polite" data-state={status.state}>{labels[status.state]}</span></header>
    <section>
      <p className="eyebrow">HERTA AGENT · WINDOWS</p>
      <h2>欢迎回来。</h2>
      {status.state === 'starting' && <p>桌面已打开，正在为你连接本机后端。</p>}
      {status.state === 'ready' && <p>本机服务已连接。当前阶段验证桌面启动与退出，聊天将在后续阶段接入。</p>}
      {status.state === 'needs_configuration' && <p>本机服务已连接；聊天模型尚未配置。配置来自启动应用时的本地环境。</p>}
      {status.state === 'unavailable' && <p className="error">{status.reason === 'start_failed'
        ? 'Python 后端启动失败，请检查本地环境后重新打开应用。'
        : status.reason === 'stop_failed' ? '后端尚未退出，请稍后关闭窗口重试。'
          : 'Python 后端已停止，请关闭并重新打开应用。'}</p>}
    </section>
    <footer><label htmlFor="message">消息</label><textarea id="message" disabled placeholder="聊天将在后续阶段开放" /><small>关闭窗口时，Herta 会一并关闭自己启动的 Python 后端。</small></footer>
  </main>;
}
