import type { MessageRecord, RunDiagnostics, RunRecord } from '../../shared/contracts';
import type { LiveRun } from '../state/run-reducer';
import { projectTools } from '../state/tool-activity';
import { AssistantMessage } from './AssistantMessage';
import { RunActivity } from './RunActivity';
import { ContextActivity } from './ContextActivity';

export function RunGroup({ records, run, live, diagnostics, diagnosticsError, onRetry }: { records: MessageRecord[]; run?: RunRecord; live?: LiveRun; diagnostics?: RunDiagnostics; diagnosticsError?: string; onRetry?: () => void }) {
  const active = live && live.phase !== 'done';
  const tools = new Map(Object.entries(active ? live.tools : {}));
  // Committed results always win over their earlier transient notifications.
  for (const tool of projectTools(records)) {
    if (tool.state !== 'declared' || !tools.has(tool.key)) tools.set(tool.key, tool);
  }
  const explanation = records.filter(r => r.message.role === 'assistant' && r.message.tool_calls.length).map(r => r.message.content).filter(Boolean).join('\n');
  return <section className="run-group">
    {records.filter(r => r.message.role === 'user').map(r => <div key={r.message_id} className="message user-message">{r.message.content}</div>)}
    {active && !records.some(r => r.message.role === 'user') && live.text && <div className="message user-message">{live.text}</div>}
    <RunActivity tools={[...tools.values()]} explanation={explanation} />
    <ContextActivity runId={run?.run_id ?? live?.runId ?? records[0]?.run_id} contexts={active ? live.contexts : diagnostics?.contexts ?? live?.contexts ?? []} diagnostics={diagnostics} error={diagnosticsError} onRetry={onRetry} />
    {records.filter(r => r.message.role === 'assistant' && !r.message.tool_calls.length).map(r => <AssistantMessage key={r.message_id} text={r.message.content ?? ''} />)}
    {active && Object.entries(live.partial).filter(([id]) => !records.some(r => r.message_id === id)).map(([id, text]) => <AssistantMessage key={id} text={text} />)}
    {active ? <p className="run-status" aria-live="polite">{{ submitting: '正在发送…', running: '正在回答…', cancelling: '正在取消…', reconciling: '正在核对保存结果…', unknown: '本轮状态待核对', done: '' }[live.phase]}</p>
      : run && <p className={'run-status' + (run.status === 'failed' ? ' error' : '')}>{({ completed: '已完成', cancelled: '本轮已取消', interrupted: '上次运行中断', failed: '本轮未完成', created: '等待运行状态', running: '运行状态待核对' })[run.status]}{run.status === 'failed' && run.error ? ` · ${run.error}` : ''}</p>}
  </section>;
}
