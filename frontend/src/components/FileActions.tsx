import { useEffect, useRef, useState } from 'react';
import type { FileJob, FilePlan, WorkspaceRoot } from '../../shared/workspace-contracts';
import { makeFileOperations } from '../state/file-operations';

const bridge = window.herta.workspace;
const kinds: Record<string, string> = { copy: '复制', move: '移动 / 改名', mkdir: '创建文件夹', publish: '保存新成果', restore_move: '恢复原位置', remove_copy: '撤销副本', remove_directory: '撤销空文件夹' };
const statuses: Record<string, string> = { queued: '等待执行', running: '正在执行', completed: '已完成', cancelled: '已停止', interrupted: '中断，请核查收据', failed: '执行失败', undone: '已撤销' };

export function FileActions({ root, selected, onChanged, incoming }: { root: WorkspaceRoot; selected: string[]; onChanged: () => Promise<void>; incoming?: FilePlan }) {
  const live = useRef(true);
  const [mode, setMode] = useState<'copy' | 'move' | 'rename' | 'organize'>('copy');
  const [folder, setFolder] = useState('整理'), [name, setName] = useState('');
  const [plan, setPlan] = useState<FilePlan>(), [plans, setPlans] = useState<FilePlan[]>([]), [jobs, setJobs] = useState<FileJob[]>([]);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  useEffect(() => { if (incoming) setPlan(incoming); }, [incoming]);
  useEffect(() => {
    live.current = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const [nextJobs, nextPlans] = await Promise.all([bridge.fileJobs(root.id), bridge.plans(root.id)]);
        if (live.current) { setJobs(nextJobs); setPlans(nextPlans); }
      } catch { if (live.current) setError('操作记录读取失败，请重新打开工作台。'); }
      finally { if (live.current) timer = setTimeout(() => void refresh(), 1000); }
    };
    void refresh();
    return () => { live.current = false; clearTimeout(timer); };
  }, [root.id]);
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); } catch (cause) { if (live.current) setError(String(cause)); }
    finally { if (live.current) setBusy(false); }
  };
  const active = jobs.some(job => ['queued', 'running'].includes(job.status));
  const execution = plan && jobs.find(job => job.plan.id === plan.id);
  return <section className="file-actions" aria-label="文件操作与收据">
    <div className="file-actions-heading"><h3>文件操作</h3><span>{selected.length} 个文件已选</span></div>
    <p className="file-note">先生成具体预览，再确认执行。不会覆盖现有文件；工程、脚本和敏感资料受保护。批量改名输入名称前缀，单文件改名输入完整文件名。</p>
    <form className="file-action-form" onSubmit={e => { e.preventDefault(); void work(async () => {
      const next = await bridge.propose(root.id, makeFileOperations(selected, mode, folder, name));
      if (live.current) { setPlan(next); setPlans(all => [next, ...all.filter(p => p.id !== next.id)]); }
    }); }}>
      <select aria-label="文件操作" value={mode} onChange={e => setMode(e.target.value as typeof mode)} disabled={busy || active}>
        <option value="copy">复制到文件夹</option><option value="move">移动到文件夹</option><option value="rename">改名</option><option value="organize">按类型整理</option>
      </select>
      {mode === 'rename' ? <input aria-label="新名称" value={name} maxLength={120} onChange={e => setName(e.target.value)} placeholder="新名称或批量前缀" /> : mode !== 'organize' && <input aria-label="目标文件夹" value={folder} maxLength={180} onChange={e => setFolder(e.target.value)} placeholder="授权目录内的相对文件夹" />}
      <button disabled={busy || active || !selected.length || (mode === 'rename' && !name.trim()) || (['copy', 'move'].includes(mode) && !folder.trim())}>生成操作预览</button>
    </form>
    {plans.length > 0 && <label className="file-history">方案记录<select aria-label="方案记录" value={plan?.id ?? ''} onChange={e => { setPlan(plans.find(p => p.id === e.target.value)); setMessage(''); }}><option value="">选择待审阅方案</option>{plans.map(p => <option value={p.id} key={p.id}>{new Date(p.created_at).toLocaleString()} · {p.undo_of ? '撤销' : '文件操作'} · {p.operations.length} 项</option>)}</select></label>}
    {plan && <div className="file-plan"><h4>{plan.undo_of ? '撤销预览' : '操作预览'} · {plan.operations.length} 项</h4><div className="file-plan-table"><table><thead><tr><th>动作</th><th>来源</th><th>目标</th></tr></thead><tbody>{plan.operations.map((op, index) => <tr key={index}><td>{kinds[op.kind] ?? op.kind}</td><td>{op.source ?? '—'}</td><td>{op.target}</td></tr>)}</tbody></table></div>
      {plan.conflicts.map((text, index) => <p key={index} className="error">{text}</p>)}
      <p className="file-note">目录：{plan.root_label} · 预览有效期 10 分钟。确认时再次检查来源和目录授权。</p>
      <button disabled={busy || active || !!plan.conflicts.length || !!execution} onClick={() => void work(async () => {
        const job = await bridge.confirm(plan.id, plan.digest);
        if (live.current) { if (job) { setJobs(all => [job, ...all.filter(j => j.id !== job.id)]); setMessage('已确认，查看执行收据。'); } else setMessage('已取消确认，文件未执行。'); }
      })}>确认此方案</button>
    </div>}
    {message && <p aria-live="polite">{message}</p>}{error && <p className="error" role="alert">{error}</p>}
    <div className="file-execution-history"><h4>执行与收据</h4>{!jobs.length && <p className="file-note">尚无执行记录。</p>}{jobs.map(job => <article key={job.id}>
      <div><strong>{statuses[job.status]}</strong><time>{new Date(job.created_at).toLocaleString()}</time></div>
      <p>{job.receipts.filter(r => r.state === 'done').length} / {job.plan.operations.length} 项已有完成收据{job.error && ` · ${job.error}`}</p>
      <details><summary>查看具体收据</summary><ul>{job.receipts.map(r => <li key={r.ordinal}>{r.state === 'done' ? '完成' : '动作已开始，完成状态未确认'} · {kinds[r.data.operation.kind]} · {r.data.operation.source && `${r.data.operation.source} → `}{r.data.operation.target}</li>)}</ul></details>
      {['queued', 'running'].includes(job.status) ? <button disabled={busy} onClick={() => void work(() => bridge.stopFile(job.id))}>停止文件任务</button> : job.status !== 'undone' && !job.plan.undo_of && job.receipts.some(r => r.state === 'done') && <button disabled={busy || active} onClick={() => void work(async () => { const next = await bridge.undo(job.id); if (live.current) setPlan(next); })}>预览撤销</button>}
    </article>)}<button disabled={busy || active} onClick={() => void work(onChanged)}>刷新目录</button></div>
  </section>;
}
