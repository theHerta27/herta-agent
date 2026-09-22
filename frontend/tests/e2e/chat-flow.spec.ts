import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';

test('real desktop chat: streaming, session switching, tools, cancel, and persisted history', async () => {
  const frontend = resolve(import.meta.dirname, '../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta Chat 中文 '));
  const env = {
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))),
    HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder, HERTA_FIXTURE_GATE: folder,
  } as Record<string, string>;
  let app: ElectronApplication | undefined;
  const launch = async () => {
    app = await electron.launch({ args: [join(frontend, 'tests/fixtures/desktop.cjs')], env, cwd: folder });
    const page = await app.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    return page;
  };
  try {
    let page = await launch();
    await expect(page.locator('.hero')).toBeVisible();
    await page.getByRole('button', { name: '切换主题' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.getByRole('button', { name: '切换主题' }).click();
    const input = page.getByRole('textbox', { name: '消息' });
    await input.fill('stream');
    await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true });
    await expect(page.locator('.user-message')).toHaveCount(0);
    await input.press('Shift+Enter');
    await expect(input).toHaveValue('stream\n');
    await input.fill('stream'); await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByText('正在生成，黑塔', { exact: true })).toBeVisible();
    await expect.poll(() => existsSync(join(folder, 'stream-entered'))).toBe(true);
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await input.fill('second'); await input.press('Enter');
    await expect(page.getByText('你好，这是离线回答。', { exact: true })).toBeVisible();
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();
    await page.getByRole('navigation', { name: '历史会话' }).getByRole('button', { name: 'stream', exact: false }).click();
    await expect(page.getByText('正在生成，黑塔', { exact: true })).toBeVisible();
    await writeFile(join(folder, 'stream-release'), '');
    await expect(page.getByText('正在生成，黑塔的完整回答。', { exact: true })).toBeVisible();
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await input.fill('tools'); await input.press('Enter');
    await expect(page.getByText('正在检索角色资料… · 2 项活动', { exact: true })).toBeVisible();
    await page.locator('.activity summary').first().click();
    await writeFile(join(folder, 'tool-release'), '');
    await expect(page.getByText('根据资料，这是离线工具回答 [fixture-1]。', { exact: true })).toBeVisible();
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();
    await expect(page.getByText('角色资料.md', { exact: false })).toBeVisible();
    await page.screenshot({ path: join(frontend, '../.local/phase6-chat-window.png') });
    await input.fill('cancel'); await input.press('Enter');
    await expect(page.getByText('未提交的半截回答', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '停止', exact: true }).click();
    await expect(page.getByText('本轮已取消', { exact: true })).toBeVisible();
    await expect(page.getByText('未提交的半截回答', { exact: true })).toHaveCount(0);
    await app!.close(); app = undefined;
    page = await launch();
    await page.getByRole('navigation', { name: '历史会话' }).getByRole('button', { name: 'tools', exact: true }).click();
    await expect(page.getByText('本轮已取消', { exact: true })).toBeVisible();
    await expect(page.getByText('根据资料，这是离线工具回答 [fixture-1]。', { exact: true })).toBeVisible();
    await expect(page.getByText('未提交的半截回答', { exact: true })).toHaveCount(0);
    await page.locator('.activity summary').first().click();
    await expect(page.getByText('角色资料.md', { exact: false })).toBeVisible();
    await app!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(800, 600));
    await expect(page.getByRole('textbox')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  } finally {
    if (app) await app.close();
    await rm(folder, { recursive: true, force: true });
  }
});
