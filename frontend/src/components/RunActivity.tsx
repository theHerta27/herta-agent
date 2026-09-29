import type { ToolActivity } from '../state/tool-activity';
import reading from '../assets/herta/status/herta-rag-reading.png';
import { PlanActivity } from './PlanActivity';
import { TestActivity, type TestOutcome } from './TestActivity';
import { ReviewActivity, type ReviewFinding } from './ReviewActivity';

export function RunActivity({ tools, explanation }: { tools: ToolActivity[]; explanation?: string }) {
  if (!tools.length && !explanation) return null;
  const running = tools.some(t => ['declared', 'running'].includes(t.state));
  const rag = tools.some(t => t.name === 'search_knowledge');
  const failed = tools.some(t => t.state === 'failed');
  const summary = running ? (rag ? '正在检索角色资料…' : '正在执行工具…')
    : failed ? '工具执行未完成' : rag ? '已检索角色资料' : '工具执行完成';
  return <details className="activity"><summary>{running && rag && <img src={reading} className="rag-icon" alt="" />}{summary} · {tools.length} 项活动</summary>
    {explanation && <p>{explanation}</p>}
    {tools.map(tool => <div className="tool-row" key={tool.key}>
      <strong>{tool.name}</strong> · Step {tool.step} · {{ declared: '等待执行', running: '执行中', completed: '完成', failed: '失败' }[tool.state] ?? tool.state}
      {tool.query && <p>检索：{tool.query}</p>}
      {tool.args && <details><summary>调用参数</summary><pre>{tool.args}</pre></details>}
      {tool.name === 'search_knowledge' && tool.state === 'completed' && <>
        {!tool.chunks?.length && <p>没有找到匹配资料。</p>}
        {tool.chunks?.map((chunk, i) => <div className="source" key={chunk.id + ':' + i}>
          <strong>[{chunk.id}]</strong> {typeof chunk.source === 'string' ? chunk.source : JSON.stringify(chunk.source)}
          {Number.isFinite(chunk.score) && <span> · 相似度 {chunk.score.toFixed(3)}</span>}
          {chunk.source_spans != null && <div>来源位置：{JSON.stringify(chunk.source_spans)}</div>}
        </div>)}
        {!!tool.chunks?.length && <p>相似度表示检索相关程度，不代表事实置信度。</p>}
      </>}
      {tool.plan && <PlanActivity steps={tool.plan} />}
      {tool.name === 'run_tests' && tool.state === 'completed' && <TestActivity result={(tool.result as { data: TestOutcome }).data} />}
      {tool.name === 'submit_review' && tool.state === 'completed' && <ReviewActivity findings={(tool.result as { data: { findings: ReviewFinding[] } }).data.findings} />}
      {tool.result != null && !tool.plan && !(['run_tests', 'submit_review'].includes(tool.name) && tool.state === 'completed') && (tool.name !== 'search_knowledge' || tool.state === 'failed') && <pre>{JSON.stringify(tool.result, null, 2)}</pre>}
    </div>)}
  </details>;
}
