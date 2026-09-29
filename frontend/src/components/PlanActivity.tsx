export interface PlanStep { title: string; rationale: string }

export function PlanActivity({ steps }: { steps: PlanStep[] }) {
  return <section className="plan-activity" aria-label="任务计划"><h3>任务计划</h3>
    <p>待执行计划 · 提议不代表完成</p>
    <ol>{steps.map((step, index) => <li key={index}><span aria-hidden="true">☐ </span><strong>{step.title}</strong><p>{step.rationale}</p></li>)}</ol>
  </section>;
}
