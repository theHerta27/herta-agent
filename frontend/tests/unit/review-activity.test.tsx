import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReviewActivity } from '../../src/components/ReviewActivity';
import { TestActivity } from '../../src/components/TestActivity';

it('renders explicit empty reviews and separates test failures from tool success', () => {
  const review = renderToStaticMarkup(<ReviewActivity findings={[]} />);
  expect(review).toContain('未报告问题');
  expect(review).not.toContain('没有任何缺陷');
  const failed = renderToStaticMarkup(<TestActivity result={{ status: 'failed', total: 1, passed: 0, failed: 1, skipped: 0, output: 'AssertionError: expected 2' }} />);
  expect(failed).toContain('测试失败');
  expect(failed).toContain('AssertionError: expected 2');
  expect(failed).not.toContain('测试通过');
});
