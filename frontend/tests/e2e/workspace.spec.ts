import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('readonly workbench persists native grants, previews a draft and reports duplicate candidates', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 文件 '));
  const chosen = join(folder, '资料');
  await mkdir(chosen);
  await writeFile(join(chosen, 'notes.md'), '学习笔记\n第二行');
  await writeFile(join(chosen, 'copy.md'), '学习笔记\n第二行');
  await writeFile(join(chosen, '.env'), 'SECRET=local');
  const before = await readFile(join(chosen, 'notes.md'));
  let desktop: ElectronApplication | undefined;
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: join(folder, 'data') } as Record<string, string>;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const page = await desktop.firstWindow();
    await expect(page.getByRole('status').first()).toHaveText('服务就绪', { timeout: 20000 });
    expect(await page.evaluate(() => Object.keys(window.herta.workspace))).toEqual(['roots', 'chooseRoot', 'share', 'revoke', 'list', 'search', 'read', 'jobs', 'start', 'cancel']);
    await desktop.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); }, chosen);
    await page.getByRole('button', { name: '文件', exact: true }).click();
    await page.getByRole('button', { name: '选择目录' }).click();
    await expect(page.getByRole('button', { name: 'notes.md', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'notes.md', exact: true }).click();
    await expect(page.locator('.file-preview')).toContainText('学习笔记');
    await page.getByRole('button', { name: '加入聊天草稿' }).click();
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue(/学习笔记/);
    await page.getByRole('button', { name: '文件', exact: true }).click();
    await page.getByRole('textbox', { name: '搜索文件名' }).fill('copy');
    await page.getByRole('button', { name: '搜索', exact: true }).click();
    await expect(page.getByRole('button', { name: 'copy.md', exact: true })).toBeVisible();
    await expect(page.getByRole('checkbox', { name: '允许聊天读取此目录' })).not.toBeChecked();
    await desktop.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 0, checkboxChecked: false }); });
    await page.getByRole('checkbox', { name: '允许聊天读取此目录' }).click();
    await expect.poll(() => page.evaluate(async () => (await window.herta.workspace.roots())[0].shared)).toBe(false);
    await desktop.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false }); });
    await page.getByRole('checkbox', { name: '允许聊天读取此目录' }).click();
    await expect(page.getByRole('checkbox', { name: '允许聊天读取此目录' })).toBeChecked();
    await page.getByRole('checkbox', { name: '检查重复候选' }).check();
    await page.getByRole('button', { name: '分析空间' }).click();
    await expect(page.locator('.analysis-report')).toContainText('copy.md', { timeout: 15000 });
    await expect(page.locator('.analysis-report')).toContainText('notes.md');
    await page.screenshot({ path: join(root, '.local/workspace-desktop.png') });
    await desktop.close(); desktop = undefined;
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const reopened = await desktop.firstWindow();
    await expect(reopened.getByRole('status').first()).toHaveText('服务就绪', { timeout: 20000 });
    await reopened.getByRole('button', { name: '文件', exact: true }).click();
    await expect(reopened.getByRole('checkbox', { name: '允许聊天读取此目录' })).toBeChecked();
    await expect(reopened.locator('.analysis-report')).toContainText('copy.md');
    await reopened.getByRole('button', { name: '撤销目录授权' }).click();
    await expect(reopened.getByText('选择一个本机目录开始。')).toBeVisible();
    expect(await readFile(join(chosen, 'notes.md'))).toEqual(before);
    expect(await readFile(join(chosen, '.env'), 'utf8')).toBe('SECRET=local');
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});

test('owned analysis can be stopped and blocks settings restart', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 分析停止 '));
  const chosen = join(folder, 'files'); await mkdir(chosen);
  for (let batch = 0; batch < 30; batch++) await Promise.all(Array.from({ length: 100 }, (_, i) => writeFile(join(chosen, `${batch}-${i}.txt`), 'local fixture')));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: join(folder, 'data') } as Record<string, string>;
  let desktop: ElectronApplication | undefined;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const page = await desktop.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    await desktop.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); }, chosen);
    const result = await page.evaluate(async () => {
      const root = await window.herta.workspace.chooseRoot();
      const settings = await window.herta.getSettings();
      const job = await window.herta.workspace.start(root!.id, true);
      let restart = '';
      try { await window.herta.applySettings(settings); } catch (error) { restart = String(error); }
      await window.herta.workspace.cancel(job.id);
      return { restart, root: root!.id };
    });
    expect(result.restart).toContain('runs_active');
    await expect.poll(() => page.evaluate(async id => (await window.herta.workspace.jobs(id))[0].status, result.root)).toBe('cancelled');
    await page.getByRole('button', { name: '文件', exact: true }).click();
    await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});
