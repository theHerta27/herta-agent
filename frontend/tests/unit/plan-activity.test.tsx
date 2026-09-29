import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PlanActivity } from '../../src/components/PlanActivity';

it('renders proposed steps as a list without falsely marking them complete', () => {
  const html = renderToStaticMarkup(<PlanActivity steps={[{ title: '读取代码', rationale: '确认现状' }, { title: '验证修改', rationale: '运行测试' }]} />);
  expect(html.match(/<li/g)).toHaveLength(2);
  expect(html).toContain('读取代码');
  expect(html).toContain('确认现状');
  expect(html).toContain('待执行');
  expect(html).not.toContain('&quot;title&quot;');
});
