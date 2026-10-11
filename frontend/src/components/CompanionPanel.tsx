import { useState, useSyncExternalStore } from 'react';
import type { CompanionPreferences, Reminder } from '../../shared/contracts';
import type { CompanionRuntime } from '../state/companion-runtime';

export function localDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value));
}

export function MiniPlayer({ runtime, onOpen }: { runtime: CompanionRuntime; onOpen: () => void }) {
  const { data } = useSyncExternalStore(runtime.subscribe, runtime.snapshot);
  if (!data) return null;
  const track = data.tracks.find(track => track.id === data.playback.track_id);
  const playing = data.playback.desired === 'playing';
  return <div className="mini-player">
    <button className="player-title" onClick={onOpen} title="打开音乐库">♫ <span>{track?.title ?? '导入音乐，陪你度过日常'}</span></button>
    <div className="player-controls"><button aria-label="上一首" disabled={!data.tracks.length} onClick={() => void runtime.action({ kind: 'music', action: 'previous' })}>‹</button>
      <button aria-label={playing ? '暂停音乐' : '播放本地音乐'} disabled={!data.tracks.length} onClick={() => void runtime.action({ kind: 'music', action: playing ? 'pause' : 'play' })}>{playing ? 'Ⅱ' : '▷'}</button>
      <button aria-label="下一首" disabled={!data.tracks.length} onClick={() => void runtime.action({ kind: 'music', action: 'next' })}>›</button>
      <span className="player-status">{{ playing: '播放中', paused: '已暂停', stopped: '已停止', pending: '准备中', error: '播放失败' }[data.playback.actual]}</span>
    </div>
  </div>;
}

function PreferencesForm({ value, runtime }: { value: CompanionPreferences; runtime: CompanionRuntime }) {
  const [draft, setDraft] = useState<Partial<CompanionPreferences>>({});
  const prefs = { ...value, ...draft };
  const edit = (change: Partial<CompanionPreferences>) => { setSaved(false); setDraft({ ...draft, ...change }); };
  const [saved, setSaved] = useState(false);
  return <form className="daily-form" onSubmit={event => { event.preventDefault(); void runtime.action({ kind: 'preferences', value: prefs }).then(ok => { setSaved(ok); if (ok) setDraft({}); }); }}>
    <label>怎么称呼你<input aria-label="称呼" value={prefs.nickname} maxLength={60} onChange={event => edit({ nickname: event.target.value })} /></label>
    <label>音乐音量 · {prefs.volume}%<input aria-label="默认音量" type="range" min="0" max="100" value={prefs.volume} onChange={event => edit({ volume: Number(event.target.value) })} /></label>
    <label className="daily-check"><input type="checkbox" checked={prefs.auto_read} onChange={event => edit({ auto_read: event.target.checked })} />自动朗读新回答</label>
    <label className="daily-check"><input type="checkbox" checked={prefs.allow_tools} onChange={event => edit({ allow_tools: event.target.checked })} />允许聊天中的日常操作</label>
    <div className="daily-time-row"><label>免打扰开始<select value={prefs.quiet_start} onChange={event => edit({ quiet_start: Number(event.target.value) })}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{hour}:00</option>)}</select></label>
      <label>免打扰结束<select value={prefs.quiet_end} onChange={event => edit({ quiet_end: Number(event.target.value) })}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{hour}:00</option>)}</select></label></div>
    <p className="daily-note">北京时间。免打扰期间保留到期提醒，稍后展示通知；起止相同表示关闭免打扰。</p>
    <button className="daily-primary" type="submit">保存偏好</button>{saved && <span className="daily-saved">已保存</span>}
    <button type="button" onClick={() => void runtime.action({ kind: 'preferences', value: { nickname: '', volume: 40, auto_read: false, allow_tools: true, quiet_start: 23, quiet_end: 8 } }).then(ok => { if (ok) { setDraft({}); setSaved(true); } })}>重置偏好</button>
  </form>;
}

export function CompanionPanel({ runtime, onClose }: { runtime: CompanionRuntime; onClose: () => void }) {
  const { data, error, voice } = useSyncExternalStore(runtime.subscribe, runtime.snapshot);
  const [title, setTitle] = useState('');
  const [due, setDue] = useState(() => new Date(Date.now() + 25 * 60000).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).replace(' ', 'T').slice(0, 16));
  const [repeat, setRepeat] = useState<Reminder['repeat']>('once');
  const [memory, setMemory] = useState('');
  const [focusBusy, setFocusBusy] = useState(false);
  return <aside className="daily-panel" aria-label="日常面板">
    <header><div><h2>日常</h2><p>音乐 · 提醒 · 记忆</p></div><button aria-label="关闭日常面板" onClick={onClose}>×</button></header>
    {error && <p className="error daily-note">{error}<button onClick={() => void runtime.refresh()}>重试</button></p>}
    {!data ? <p>正在读取日常数据…</p> : <>
      <button className="focus-routine" disabled={focusBusy} onClick={() => { setFocusBusy(true); void runtime.focus().finally(() => setFocusBusy(false)); }}><strong>45<span>分钟</span></strong><div>开始专注<small>启动计时，有音乐时继续播放</small></div><span>→</span></button>
      {data.deliveries.length > 0 && <section className="daily-section"><h3>到期提醒</h3>{data.deliveries.map(item => <div className="delivery-item" key={item.id}><strong>{item.title}</strong><small>原定 {localDate(item.due_at)}</small><div><button onClick={() => void runtime.action({ kind: 'ack', id: item.id })}>知道了</button><button onClick={() => void runtime.action({ kind: 'snooze', id: item.reminder_id, minutes: 10 })}>10分钟后</button></div></div>)}</section>}
      <section className="daily-section"><h3>本地音乐<button onClick={() => void runtime.importMusic()}>导入</button></h3>
        {!data.tracks.length && <p className="daily-note">选择你电脑上的音乐文件。之后可以直接说“放首歌”。</p>}
        <div className="music-library">{data.tracks.map(track => <button key={track.id} className={track.id === data.playback.track_id ? 'selected' : ''} onClick={() => void runtime.action({ kind: 'music', action: 'play', track_id: track.id })}><span>♫</span>{track.title}</button>)}</div>
      </section>
      <section className="daily-section"><h3>提醒</h3><form className="daily-form" onSubmit={event => { event.preventDefault(); if (title.trim()) void runtime.action({ kind: 'create_reminder', title, due_at: due + ':00+08:00', repeat }).then(ok => { if (ok) setTitle(''); }); }}>
        <input aria-label="提醒内容" placeholder="提醒我做什么？" value={title} maxLength={200} onChange={event => setTitle(event.target.value)} required />
        <div className="daily-time-row"><input aria-label="提醒时间" type="datetime-local" value={due} onChange={event => setDue(event.target.value)} required /><select aria-label="重复规则" value={repeat} onChange={event => setRepeat(event.target.value as Reminder['repeat'])}><option value="once">一次</option><option value="daily">每天</option><option value="weekly">每周</option></select></div>
        <button className="daily-primary" type="submit" disabled={!title.trim()}>添加提醒</button>
      </form>
      {data.reminders.map(item => <div className="reminder-item" key={item.id}><div><strong>{item.title}</strong><small>{localDate(item.due_at)} · {{ once: '一次', daily: '每天', weekly: '每周' }[item.repeat]}{!item.enabled && ' · 已停用'}</small></div>{item.enabled && <button onClick={() => void runtime.action({ kind: 'cancel_reminder', id: item.id })}>取消</button>}</div>)}
      <p className="daily-note">关闭窗口后在托盘继续提醒。完全退出期间不运行，重开后显示错过的提醒。</p></section>
      <section className="daily-section"><h3>偏好</h3><PreferencesForm value={data.preferences} runtime={runtime} /></section>
      <section className="daily-section"><h3>记忆</h3><form className="daily-form" onSubmit={event => { event.preventDefault(); void runtime.action({ kind: 'memory', text: memory }).then(ok => { if (ok) setMemory(''); }); }}><input aria-label="记住一件事" value={memory} maxLength={200} placeholder="希望黑塔记住的一件事" onChange={event => setMemory(event.target.value)} /><button disabled={!memory.trim()}>添加记忆</button></form>
        {data.memories.map(item => <div className="memory-item" key={item.id}><p>{item.text}</p><div><small>{item.status === 'pending' ? '待确认' : '已保存'}</small>{item.status === 'pending' && <button onClick={() => void runtime.action({ kind: 'approve_memory', id: item.id })}>保存</button>}<button onClick={() => void runtime.action({ kind: 'delete_memory', id: item.id })}>删除</button></div></div>)}
        <p className="daily-note">只有你保存的记忆会用于后续回答。删除后不再加入新一轮对话。</p>
      </section>
      <p className="daily-note voice-detail">{voice.detail} · Ctrl+Shift+H 唤出 Herta</p>
    </>}
  </aside>;
}
