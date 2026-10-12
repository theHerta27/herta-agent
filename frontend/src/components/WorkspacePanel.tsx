import { useEffect, useRef, useState } from 'react';
import type { AnalysisJob, FileListing, TextPreview, WorkspaceRoot, FilePlan } from '../../shared/workspace-contracts';
import '../styles/files.css';
import { FileActions } from './FileActions';
import { DocumentsPanel } from './DocumentsPanel';

const bridge = window.herta.workspace;
const hints: Record<string, string> = { folder: '文件夹', file: '文件', project: '工程 · 整体保留', cache: '缓存 · 仅统计', protected: '受保护', link: '链接 · 不读取', shortcut: '快捷方式' };
const statuses: Record<string, string> = { running: '正在分析', completed: '已完成', cancelled: '已停止', interrupted: '上次退出时中断', failed: '分析失败' };
function bytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let size = value / 1024, index = 0;
  while (size >= 1024 && index < 3) { size /= 1024; index++; }
  return `${size.toFixed(1)} ${units[index]}`;
}

export function WorkspacePanel({ onClose, onDraft }: { onClose: () => void; onDraft: (text: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null), live = useRef(true);
  const [roots, setRoots] = useState<WorkspaceRoot[]>([]), [selected, setSelected] = useState('');
  const [error, setError] = useState(''), [choosing, setChoosing] = useState(false);
  useEffect(() => {
    live.current = true; dialog.current?.showModal();
    void bridge.roots().then(value => { if (live.current) { setRoots(value); setSelected(value[0]?.id ?? ''); } }).catch(() => { if (live.current) setError('目录读取失败，请关闭后重试。'); });
    return () => { live.current = false; };
  }, []);
  const choose = async () => {
    setChoosing(true); setError('');
    try { const root = await bridge.chooseRoot(); const all = await bridge.roots(); if (live.current) { setRoots(all); if (root) setSelected(root.id); } }
    catch (cause) { if (live.current) setError(String(cause)); }
    finally { if (live.current) setChoosing(false); }
  };
  const root = roots.find(r => r.id === selected);
  return <dialog className="file-workbench" ref={dialog} onCancel={onClose} aria-labelledby="files-title">
    <header><div><h2 id="files-title">文件工作台</h2><p>浏览资料，了解占用；审阅并确认具体文件方案。</p></div><button onClick={onClose}>关闭文件工作台</button></header>
    <div className="file-layout"><aside className="file-roots"><button onClick={() => void choose()} disabled={choosing}>{choosing ? '正在选择…' : '选择目录'}</button><p>本机授权目录</p>
      {roots.map(r => <button key={r.id} aria-pressed={r.id === selected} onClick={() => setSelected(r.id)}>{r.label}<small>{r.shared ? '聊天可读取' : '仅本地查看'}</small></button>)}
      {!roots.length && <p>选择一个本机目录开始。</p>}{error && <p className="error" role="alert">{error}</p>}
    </aside>{root ? <WorkspaceFolder key={root.id} root={root} onRoot={next => setRoots(all => all.map(r => r.id === next.id ? next : r))} onRevoke={() => { setRoots(all => all.filter(r => r.id !== root.id)); setSelected(''); }} onDraft={text => { onDraft(text); onClose(); }} /> : <div className="file-empty">选择目录后，可以浏览文件、预览文本或分析空间。工程与敏感文件会分别标注。</div>}</div>
  </dialog>;
}

function WorkspaceFolder({ root, onRoot, onRevoke, onDraft }: { root: WorkspaceRoot; onRoot: (root: WorkspaceRoot) => void; onRevoke: () => void; onDraft: (text: string) => void }) {
  const live = useRef(true), revision = useRef(0);
  const [path, setPath] = useState(''), [query, setQuery] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [incomingPlan, setIncomingPlan] = useState<FilePlan>();
  const [listing, setListing] = useState<FileListing>(), [preview, setPreview] = useState<TextPreview>();
  const [jobs, setJobs] = useState<AnalysisJob[]>([]), [jobId, setJobId] = useState('');
  const [duplicates, setDuplicates] = useState(false), [error, setError] = useState(''), [pending, setPending] = useState(false);
  const action = async (work: () => Promise<void>) => {
    setError(''); setPending(true);
    try { await work(); } catch (cause) { if (live.current) setError(String(cause)); }
    finally { if (live.current) setPending(false); }
  };
  const browse = async (next: string) => {
    const version = ++revision.current; setPreview(undefined); setSelectedFiles([]);
    const value = await bridge.list(root.id, next);
    if (live.current && version === revision.current) { setListing(value); setPath(next); setQuery(''); }
  };
  useEffect(() => {
    live.current = true; void action(() => browse(''));
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try { const value = await bridge.jobs(root.id); if (live.current) setJobs(value); }
      catch { if (live.current) setError('分析记录读取失败，请关闭后重试。'); }
      finally { if (live.current) timer = setTimeout(() => void refresh(), 1000); }
    };
    void refresh();
    return () => { live.current = false; revision.current++; clearTimeout(timer); };
    // Root changes remount this component, isolating all request lifetimes.
  }, [root.id]);
  const active = jobs.find(j => j.status === 'running'), job = jobs.find(j => j.id === jobId) ?? jobs[0], report = job?.report;
  return <div className="file-content">
    <div className="file-permissions"><label><input type="checkbox" checked={root.shared} disabled={pending} onChange={e => { const enabled = e.target.checked; void action(async () => { const next = await bridge.share(root.id, enabled); if (live.current) onRoot(next); }); }} />允许聊天读取此目录</label><button disabled={pending} onClick={() => void action(async () => { await bridge.revoke(root.id); if (live.current) onRevoke(); })}>撤销目录授权</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="file-columns"><section className="file-browser" aria-label="目录浏览"><div className="file-breadcrumb"><button disabled={pending} onClick={() => void action(() => browse(''))}>{root.label}</button><span> / {path || '根目录'}</span>{path && <button disabled={pending} onClick={() => void action(() => browse(path.split('/').slice(0, -1).join('/')))}>上一级</button>}</div>
      <form className="file-search" onSubmit={e => { e.preventDefault(); void action(async () => { revision.current++; setPreview(undefined); const value = await bridge.search(root.id, query); if (live.current) setListing(value); }); }}><input aria-label="搜索文件名" placeholder="按名称查找文件" value={query} maxLength={80} onChange={e => setQuery(e.target.value)} /><button disabled={pending || !query.trim()}>搜索</button></form>
      <div className="file-table"><table><thead><tr><th>名称</th><th>类别</th><th>大小</th></tr></thead><tbody>{listing?.entries.map(entry => <tr key={entry.path}><td>{entry.kind === 'file' && entry.hint === 'file' && <input type="checkbox" aria-label={`选择 ${entry.name}`} checked={selectedFiles.includes(entry.path)} onChange={e => setSelectedFiles(all => e.target.checked ? [...all, entry.path] : all.filter(p => p !== entry.path))} />}<button disabled={pending || ['link', 'protected', 'cache', 'shortcut'].includes(entry.hint)} title={entry.path} onClick={() => void action(async () => { if (entry.kind === 'directory') await browse(entry.path); else { const value = await bridge.read(root.id, entry.path); if (live.current) setPreview(value); } })}>{entry.name}</button>{!listing.path && entry.path !== entry.name && <small>{entry.path}</small>}</td><td>{hints[entry.hint] ?? entry.hint}</td><td>{entry.kind === 'file' ? bytes(entry.size) : '—'}</td></tr>)}</tbody></table>{listing?.entries.length === 0 && <p>没有找到文件。</p>}</div>
      {listing?.truncated && <p className="file-note">结果已截断，请进入子目录或缩小搜索范围。</p>}
      {preview && <div className="file-preview"><strong>{preview.path}</strong><span> · 从第 {preview.start_line} 行</span><pre>{preview.text}</pre>{preview.truncated && <p>仅展示文本前部。</p>}<button onClick={() => onDraft(`资料：${root.label}/${preview.path}（从第1行${preview.truncated ? '，已截断' : ''}）\n\n${preview.text}`)}>加入聊天草稿</button><p className="file-note">加入后可编辑；点击发送才会交给聊天模型。</p></div>}
    </section><section className="file-analysis" aria-label="空间分析"><h3>空间分析</h3><label><input type="checkbox" checked={duplicates} onChange={e => setDuplicates(e.target.checked)} disabled={pending || !!active} />检查重复候选</label><div className="file-analysis-actions"><button disabled={pending || !!active} onClick={() => void action(async () => { const next = await bridge.start(root.id, duplicates); if (live.current) { setJobs(all => [next, ...all]); setJobId(next.id); } })}>分析空间</button>{active && <button disabled={pending} onClick={() => void action(() => bridge.cancel(active.id))}>停止分析</button>}</div>
      {jobs.length > 0 && <label className="file-history">分析记录<select aria-label="分析记录" value={job?.id} onChange={e => setJobId(e.target.value)}>{jobs.map(j => <option key={j.id} value={j.id}>{new Date(j.created_at).toLocaleString()} · {statuses[j.status]}</option>)}</select></label>}{job && <p aria-live="polite">{statuses[job.status]}{job.error && `：${job.error}`}</p>}
      {report && <div className="analysis-report"><dl><dt>所在磁盘已用 / 总容量</dt><dd>{bytes(report.disk.used)} / {bytes(report.disk.total)}</dd><dt>磁盘可用</dt><dd>{bytes(report.disk.free)}</dd><dt>目录内已扫描的逻辑大小</dt><dd>{bytes(report.logical_bytes)}</dd></dl><p className="file-note">{report.entries} 项 · 跳过 {report.skipped} 项{report.partial ? ' · 有限范围报告' : ''}。逻辑大小包含缓存，可能重复计入硬链接；不能等同实际可释放空间。</p>
        <h4>大文件</h4><ol>{report.files.slice(0, 10).map(f => <li key={f.path}><span>{f.path}</span><b>{bytes(f.size)}</b></li>)}</ol><h4>目录占用</h4><ol>{report.directories.slice(0, 10).map(d => <li key={d.path}><span>{d.path}<small>{hints[d.hint]}</small></span><b>{bytes(d.size)}</b></li>)}</ol>
        <h4>重复候选</h4>{report.duplicates.length ? report.duplicates.map((group, index) => <p key={index}>{group.paths.join(' · ')}<small>{group.count} 个内容相同的文件 · 每个 {bytes(group.size)}；用途仍需人工判断。</small></p>) : <p className="file-note">{report.duplicates_checked ? '检查范围内未发现重复候选。' : '本次未读取文件内容检查重复。'}</p>}
        {report.suggestions.map(text => <p className="file-note" key={text}>{text}</p>)}<details><summary>分析范围与限制</summary><p>{report.limits}</p></details>
      </div>}
    </section></div>
    <DocumentsPanel root={root} selected={selectedFiles} onPlan={setIncomingPlan} onDraft={onDraft} />
    <FileActions root={root} selected={selectedFiles} incoming={incomingPlan} onChanged={() => browse(path)} />
  </div>;
}
