import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('coding desktop reads, plans, patches, reports real test outcomes and reviews read-only', async () => {
  test.skip(process.env.HERTA_DOCKER_TESTS !== '1', 'requires real Docker Desktop and sandbox image');
  const frontend = resolve(import.meta.dirname, '../..');
  const folder = await mkdtemp(join(tmpdir(), 'Coding 桌面 '));
  const source = join(folder, 'repo');
  await mkdir(join(source, 'tests'), { recursive: true });
  await writeFile(join(source, 'calc.py'), 'def value():\n    return 1\n');
  await writeFile(join(source, 'tests/test_calc.py'), 'import unittest\nfrom calc import value\nclass Test(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 2)\n');
  const env = {
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && key !== 'ELECTRON_RUN_AS_NODE')),
    PYTHONPATH: resolve(frontend, '../backend'), HERTA_SERVICE_PROVIDER: 'demo', HERTA_CODING_REPO_ROOT: source,
    HERTA_DESKTOP_DATA_DIR: join(folder, 'data'), HERTA_CODING_MODE: 'coding',
  } as Record<string, string>;
  let app: ElectronApplication | undefined;
  const launch = async () => {
    app = await electron.launch({ args: [join(frontend, 'tests/fixtures/coding-desktop.cjs')], env, cwd: folder });
    const page = await app.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    return page;
  };
  try {
    let page = await launch();
    const send = async (text: string) => {
      await page.getByRole('button', { name: '新对话', exact: true }).click();
      await page.getByRole('textbox').fill(text);
      await page.getByRole('textbox').press('Enter');
      await expect(page.getByText('已完成', { exact: true })).toBeVisible();
      await page.locator('.activity summary').first().click();
    };
    await send('read');
    await expect(page.getByText('定义在 calc.py:1，读取已核对。', { exact: true })).toBeVisible();
    await expect(page.locator('.tool-row strong', { hasText: 'read_file' })).toBeVisible();
    await send('change');
    await expect(page.getByRole('region', { name: '任务计划' })).toBeVisible();
    await expect(page.getByText('测试通过', { exact: true })).toBeVisible();
    await expect(page.getByText('测试失败', { exact: true })).toBeVisible();
    expect(await readFile(join(source, 'calc.py'), 'utf8')).toContain('return 1');
    expect(await readFile(join(source, '.coding-agent-workspace/calc.py'), 'utf8')).toContain('return 2');
    await send('break');
    await expect(page.getByText('测试失败', { exact: true })).toBeVisible();
    await expect(page.getByText('测试通过', { exact: true })).toHaveCount(0);
    await app!.close(); app = undefined;
    env.HERTA_CODING_MODE = 'review';
    page = await launch();
    await send('review');
    await expect(page.getByRole('region', { name: '代码评审' })).toBeVisible();
    await expect(page.getByText('潜在缺陷 · 返回值违反测试约定')).toBeVisible();
    expect(await readFile(join(source, '.coding-agent-workspace/calc.py'), 'utf8')).toContain('return 3');
    await page.screenshot({ path: resolve(frontend, '../.local/coding-desktop.png') });
  } finally {
    if (app) await app.close();
    await rm(folder, { recursive: true, force: true });
  }
});
