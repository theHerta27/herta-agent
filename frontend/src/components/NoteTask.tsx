import { useEffect, useRef, useState } from 'react';
import type { FileJob, FilePlan, TextPreview } from '../../shared/workspace-contracts';
import { loadNotePlan, noteResult, type NoteProposal, type NoteVerified } from '../state/note-task';
import '../styles/note-task.css';

const bridge = window.herta.workspace;

export function NoteTask({ proposal, sessionId, taskBusy, onVerified }: { proposal: NoteProposal; sessionId: string; taskBusy: boolean; onVerified?: NoteVerified }) {
  const live = useRef(true), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0), verifyAfterSave = useRef(false), callback = useRef(onVerified);
  callback.current = onVerified;
  const [plan, setPlan] = useState<FilePlan>(), [job, setJob] = useState<FileJob>(), [preview, setPreview] = useState<TextPreview>();
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const report = async (current: FilePlan) => {
    try {
      const sent = await callback.current?.(sessionId, current);
      if (live.current) setNotice(sent ? '' : '笔记已保存，聊天续接尚未发送；可稍后点击让 Herta 核对结果。');
    } catch { if (live.current) setNotice('笔记已保存，聊天续接尚未确认；请先查看聊天状态。'); }
  };
  const refresh = async () => {
    const version = ++generation.current;
    clearTimeout(timer.current);
    try {
      const next = await loadNotePlan(bridge, proposal);
      const result = await noteResult(bridge, next);
      if (!live.current || version !== generation.current) return;
      setPlan(next.plan); setJob(result.job ?? undefined); setPreview(result.preview); setError('');
      if (result.job && ['queued', 'running'].includes(result.job.status)) timer.current = setTimeout(() => void refresh(), 500);
      if (result.preview && verifyAfterSave.current) { verifyAfterSave.current = false; await report(next.plan); }
    } catch (cause) { if (live.current && version === generation.current) { setPlan(undefined); setJob(undefined); setPreview(undefined); setError(String(cause)); } }
  };
  useEffect(() => {
    live.current = true; void refresh();
    return () => { live.current = false; generation.current++; clearTimeout(timer.current); };
  }, [proposal.planId]);
  const confirm = async () => {
    if (!plan || busy || taskBusy) return;
    setBusy(true); setNotice('');
    try {
      const current = await loadNotePlan(bridge, proposal);
      const result = await bridge.confirm(current.plan.id, current.plan.digest);
      if (live.current && !result) setNotice('已取消确认，文件未保存。');
      if (live.current && result) verifyAfterSave.current = true;
      await refresh();
    } catch (cause) { if (live.current) setError(String(cause)); }
    finally { if (live.current) setBusy(false); }
  };
  const status = preview ? '已保存并读取目标文件，内容核对一致。' : job ? ({ queued: '等待文件执行。', running: '正在保存。', completed: '执行已完成，正在核对内容。', cancelled: '文件任务已停止，请核对完成收据。', failed: '保存失败。', interrupted: '上次执行中断，请核对收据。', undone: '该笔记已撤销。' })[job.status] : error ? '当前保存状态无法核对。' : '笔记待确认，尚未写入目标文件。';
  return <section className="note-task" aria-label="笔记保存任务">
    <header><strong>笔记预览</strong>{plan && <span>{plan.root_label} / {plan.operations.find(op => op.kind === 'publish')?.target}</span>}</header>
    <p aria-live="polite">{status}</p>
    <pre className="note-content">{preview?.text ?? proposal.text}</pre>
    {preview?.truncated && <p>正文较长，仅显示预览；已核对完整文件内容。</p>}
    {plan?.conflicts.map((value, index) => <p className="error" key={index}>{value}</p>)}
    {job && <p>完成收据：{job.receipts.filter(r => r.state === 'done').length} / {job.plan.operations.length} 项{job.error && ` · ${job.error}`}</p>}
    {notice && <p aria-live="polite">{notice}</p>}{error && <p className="error" role="alert">{error}</p>}
    <footer><button disabled={taskBusy || busy || !plan || !!plan.conflicts.length || !!job} onClick={() => void confirm()}>{busy ? '正在确认…' : '确认保存笔记'}</button><button disabled={busy} onClick={() => void refresh()}>刷新保存状态</button>{preview && <button disabled={taskBusy || busy} onClick={() => plan && void report(plan)}>让 Herta 核对结果</button>}</footer>
    {!job && <small>确认会显示原生对话框；预览有效期10分钟，已有文件不会覆盖。保存完成后会在本会话继续核对结果。</small>}
  </section>;
}
