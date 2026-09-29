export interface TestOutcome { status: string; total: number | null; passed: number | null; failed: number | null; skipped: number | null; output: string }

export function TestActivity({ result }: { result: TestOutcome }) {
  return <section aria-label="测试结果"><strong>{result.status === 'passed' ? '测试通过' : '测试失败'}</strong>
    <p>总数 {result.total ?? '未知'} · 通过 {result.passed ?? '未知'} · 失败 {result.failed ?? '未知'} · 跳过 {result.skipped ?? '未知'}</p>
    <pre>{result.output}</pre>
  </section>;
}
