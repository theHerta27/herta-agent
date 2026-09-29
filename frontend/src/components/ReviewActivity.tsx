export interface ReviewFinding { category: 'style' | 'bug' | 'tests'; title: string; path: string; start_line: number; end_line: number; explanation: string }

export function ReviewActivity({ findings }: { findings: ReviewFinding[] }) {
  return <section aria-label="代码评审"><h3>代码评审</h3>
    {!findings.length && <p>本次评审未报告问题。</p>}
    {findings.map((finding, index) => <article key={index}>
      <strong>{({ style: '风格规范', bug: '潜在缺陷', tests: '缺失测试' })[finding.category]} · {finding.title}</strong>
      <p>{finding.path}:{finding.start_line}–{finding.end_line}</p><p>{finding.explanation}</p>
    </article>)}
  </section>;
}
