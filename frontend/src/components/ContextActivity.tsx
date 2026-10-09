import type { ContextDiagnostic, RunDiagnostics } from '../../shared/contracts';

export function ContextActivity({ runId, contexts, diagnostics, error, onRetry }: { runId?: string; contexts: ContextDiagnostic[]; diagnostics?: RunDiagnostics; error?: string; onRetry?: () => void }) {
  if (!contexts.length && !diagnostics && !error) return null;
  return <details className="activity context-activity"><summary>上下文诊断 · {contexts.length} 个步骤</summary>
    {runId && <p className="context-run">Run <code>{runId}</code></p>}
    <p>Token 为估算值，不是账单用量。</p>
    {error && <p className="error">{error}{onRetry && <button onClick={onRetry}>重试诊断</button>}</p>}
    {!contexts.length && !error && <p>本轮没有可用的上下文诊断。</p>}
    {contexts.map(context => <div className="tool-row context-step" key={context.step}>
      <strong>Step {context.step}</strong>
      <dl>
        <dt>估算输入</dt><dd>{context.estimated_input_tokens.toLocaleString()} / {context.input_budget.toLocaleString()} Token</dd>
        <dt>工具定义</dt><dd>{context.tool_schema_tokens.toLocaleString()} Token</dd>
        <dt>保留消息索引</dt><dd>{context.retained_message_indices.join(', ') || '无'}（从 0 开始）</dd>
        <dt>省略消息</dt><dd>{context.omitted_message_count} 条</dd>
        <dt>选择原因</dt><dd>{context.reason}</dd>
        <dt>策略版本</dt><dd>{context.policy_version}</dd>
        <dt>Persona hash</dt><dd><code>{context.persona_hash}</code></dd>
        <dt>证据引用</dt><dd>{context.evidence_refs.join(', ') || '无'}</dd>
      </dl>
      {!!context.summary_refs.length && <details><summary>旧历史摘要 · {context.summary_refs.length} 项</summary>{context.summary_refs.map(ref => <dl key={ref.summary_id}>
        <dt>摘要 ID</dt><dd>{ref.summary_id}</dd><dt>来源范围</dt><dd>{ref.source_start}–{ref.source_end}</dd>
        <dt>来源 hash</dt><dd><code>{ref.source_hash}</code></dd><dt>算法</dt><dd>{ref.algorithm}</dd>
      </dl>)}</details>}
    </div>)}
    {!!diagnostics?.tools.length && <details><summary>工具执行诊断 · {diagnostics.tools.length} 项</summary>{diagnostics.tools.map((tool, index) => <div className="tool-row" key={index}><pre>{JSON.stringify(tool, null, 2)}</pre></div>)}</details>}
  </details>;
}