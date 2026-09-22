export interface SidebarSession { session_id: string; title: string; active?: boolean }
export function ConversationSidebar({ sessions, selected, onSelect, onNew, collapsed, onToggle, light, onTheme }: {
  sessions: SidebarSession[]; selected: string | null; onSelect: (id: string) => void; onNew: () => void;
  collapsed: boolean; onToggle: () => void; light: boolean; onTheme: () => void;
}) {
  return <aside className={'sidebar' + (collapsed ? ' collapsed' : '')}>
    <div className="sidebar-brand"><strong>Herta</strong><button className="icon" aria-label={collapsed ? '展开侧栏' : '折叠侧栏'} onClick={onToggle}>☰</button></div>
    <button className="new-chat" onClick={onNew} aria-label="新对话">＋ <span>新对话</span></button>
    {!collapsed && <><p className="sidebar-label">桌面会话</p><nav aria-label="历史会话">
      {sessions.length === 0 && <p className="sidebar-empty">你的对话会保存在这里</p>}
      {sessions.map(session => <button key={session.session_id} className={'session-row' + (selected === session.session_id ? ' selected' : '')} onClick={() => onSelect(session.session_id)} title={session.title}>
        <span>{session.title}</span>{session.active && <small aria-label="运行中">●</small>}
      </button>)}
    </nav></>}
    <button className="theme-toggle" aria-label="切换主题" onClick={onTheme}>{light ? '◐' : '☼'} {!collapsed && (light ? '深色外观' : '浅色外观')}</button>
  </aside>;
}
