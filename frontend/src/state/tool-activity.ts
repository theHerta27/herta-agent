import type { MessageRecord, ServiceEvent, ToolCall } from '../../shared/contracts';
export interface Evidence { id: string; source: string; score: number; source_spans?: unknown }
export interface ToolActivity { key: string; step: number; id: string; name: string; args?: string; state: string; chunks?: Evidence[]; query?: string; result?: unknown }
const keyFor = (run: string, step: number, id: string) => `${run}:${step}:${id}`;

function result(tool: ToolActivity, value: unknown): ToolActivity {
  const outcome = value as { ok?: boolean; data?: { query?: string; chunks?: Evidence[] } } | null;
  return { ...tool, state: outcome?.ok ? 'completed' : 'failed', result: value,
    query: outcome?.data?.query ?? tool.query, chunks: outcome?.data?.chunks };
}

export function applyToolEvent(tools: Record<string, ToolActivity>, event: ServiceEvent) {
  const next = { ...tools };
  const p = event.payload;
  const step = Number(p.step ?? 0);
  const message = p.message as { tool_calls?: ToolCall[] } | undefined;
  if (event.type === 'llm.completed') for (const call of message?.tool_calls ?? []) {
    const key = keyFor(event.run_id, step, call.id);
    next[key] = { key, step, id: call.id, name: call.name, args: call.arguments, state: 'declared' };
  }
  if (event.type.startsWith('tool.') || event.type === 'rag.retrieved') {
    const id = String(p.tool_call_id);
    const key = keyFor(event.run_id, step, id);
    let tool = next[key] ?? { key, step, id, name: String(p.name ?? 'search_knowledge'), state: 'declared' };
    if (event.type === 'tool.started') tool = { ...tool, state: 'running' };
    if (['tool.completed', 'tool.failed'].includes(event.type)) tool = result(tool, p.result);
    if (event.type === 'rag.retrieved') tool = { ...tool, query: String(p.query ?? ''), chunks: p.chunks as Evidence[] };
    next[key] = tool;
  }
  return next;
}

export function projectTools(records: MessageRecord[]): ToolActivity[] {
  const tools: Record<string, ToolActivity> = {};
  for (const record of records) {
    const m = record.message;
    if (m.role === 'assistant') for (const call of m.tool_calls ?? []) {
      const key = keyFor(record.run_id, record.step, call.id);
      tools[key] = { key, step: record.step, id: call.id, name: call.name, args: call.arguments, state: 'declared' };
    }
    if (m.role === 'tool') {
      const key = keyFor(record.run_id, record.step, m.tool_call_id!);
      const tool = tools[key] ?? { key, step: record.step, id: m.tool_call_id!, name: '工具', state: 'declared' };
      try { tools[key] = result(tool, JSON.parse(m.content ?? 'null')); }
      catch { tools[key] = { ...tool, state: 'failed', result: { error: { message: '结果无法读取' } } }; }
    }
  }
  return Object.values(tools);
}
