import type { Conversation } from '../state/chat-store';
import type { MessageRecord } from '../../shared/contracts';
import { RunGroup } from './RunGroup';

export function MessageList({ view, onRetryDiagnostics }: { view: Conversation; onRetryDiagnostics?: () => void }) {
  const groups = new Map<string, MessageRecord[]>();
  for (const record of view.messages) {
    if (!groups.has(record.run_id)) groups.set(record.run_id, []);
    groups.get(record.run_id)!.push(record);
  }
  const live = view.request;
  const activeId = live?.runId ?? live?.id;
  if (live && live.phase !== 'done' && activeId && !groups.has(activeId)) groups.set(activeId, []);
  return <div className="content">{[...groups].map(([id, records]) => <RunGroup key={id} records={records} run={view.runs[id]} diagnostics={view.diagnostics[id]} diagnosticsError={view.diagnosticsErrors[id]} onRetry={onRetryDiagnostics} live={id === activeId ? live : undefined} />)}</div>;
}
