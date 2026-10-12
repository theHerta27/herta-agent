import { _electron as electron, expect, test } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('sharing previews copied text before inserting a bounded draft and screenshots only the owned test window', async () => {
  const root = resolve(import.meta.dirname, '../../..'); const folder = await mkdtemp(join(tmpdir(), 'Herta 分享 '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('HERTA_') && k !== 'ELECTRON_RUN_AS_NODE')), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder };
  const app = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
  try {
    const page = await app.firstWindow(); await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    await app.evaluate(({ clipboard }) => { clipboard.readText = async () => '用户主动复制的测试资料'; });
    await page.getByRole('button', { name: '附加', exact: true }).click();
    await page.getByRole('button', { name: '读取已复制文字' }).click();
    await expect(page.getByRole('textbox', { name: '共享文字预览' })).toHaveValue('用户主动复制的测试资料');
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue('');
    await page.getByRole('button', { name: '确认加入当前草稿' }).click();
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue(/用户主动复制的测试资料/);
    await page.getByRole('button', { name: '附加', exact: true }).click();
    await page.getByRole('button', { name: '选择截图窗口' }).click();
    const choice = page.getByRole('combobox', { name: '截图对象' });
    await expect(choice).toContainText('Herta');
    const own = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getMediaSourceId());
    await choice.selectOption(own);
    await page.getByRole('button', { name: '拍摄并预览' }).click();
    await expect(page.getByRole('img', { name: '本次截图预览' })).toBeVisible();
    await page.getByRole('button', { name: '本地识别文字' }).click();
    await expect(page.getByText(/Windows.Media.Ocr/)).toBeVisible({ timeout: 40000 });
    await page.getByRole('button', { name: '取消共享' }).click();
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue(/用户主动复制的测试资料/);
  } finally { await app.close(); await rm(folder, { recursive: true, force: true }); }
});
