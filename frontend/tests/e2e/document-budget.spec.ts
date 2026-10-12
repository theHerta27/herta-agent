import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('long document fits the current draft and a full draft is preserved', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 长资料 '));
  const chosen = join(folder, '资料'); await mkdir(chosen);
  await writeFile(join(chosen, '长文.txt'), '第一段引用内容。'.repeat(2000));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: join(folder, 'data') } as Record<string, string>;
  let desktop: ElectronApplication | undefined;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const page = await desktop.firstWindow();
    await expect(page.getByRole('status').first()).toHaveText('服务就绪', { timeout: 20000 });
    const original = 'x'.repeat(9950);
    await page.getByRole('textbox', { name: '消息' }).fill(original);
    await desktop.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); }, chosen);
    await page.getByRole('button', { name: '文件', exact: true }).click();
    await page.getByRole('button', { name: '选择目录' }).click();
    await page.getByRole('checkbox', { name: '选择 长文.txt' }).check();
    await page.getByRole('button', { name: '阅读选中文档' }).click();
    await expect(page.locator('.document-preview')).toContainText('长文.txt#行1');
    await page.getByRole('button', { name: '请求整理学习笔记' }).click();
    await expect(page.getByText(/当前草稿空间不足/)).toBeVisible();
    await page.getByRole('button', { name: '关闭文件工作台' }).click();
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue(original);
    await page.getByRole('textbox', { name: '消息' }).fill('我的问题');
    await page.getByRole('button', { name: '文件', exact: true }).click();
    await page.getByRole('checkbox', { name: '选择 长文.txt' }).check();
    await page.getByRole('button', { name: '阅读选中文档' }).click();
    await expect(page.locator('.document-preview')).toContainText('长文.txt#行1');
    await page.getByRole('button', { name: '请求整理学习笔记' }).click();
    const draft = await page.getByRole('textbox', { name: '消息' }).inputValue();
    expect(draft.length).toBeLessThanOrEqual(10000);
    expect(draft.startsWith('我的问题\n\n')).toBe(true);
    expect(draft).toContain('[长文.txt#行1]');
    expect(draft).toContain('已按当前草稿余量截取');
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.locator('.user-message').last()).toContainText('长文.txt#行1');
    await expect(page.getByRole('button', { name: '停止', exact: true })).not.toBeVisible({ timeout: 20000 });
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});
