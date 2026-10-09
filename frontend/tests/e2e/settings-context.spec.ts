import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';

test('public settings restart the backend, refuse busy runs and persist diagnostics across reopen', async () => {
  test.setTimeout(90000);
  const frontend = resolve(import.meta.dirname, '../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 设置 中文 '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder, HERTA_FIXTURE_GATE: folder, HERTA_API_KEY: 'test-secret', HERTA_EMBEDDING_API_KEY: 'embedding-secret' } as Record<string, string>;
  let app: ElectronApplication | undefined;
  const launch = async () => {
    app = await electron.launch({ args: [join(frontend, 'tests/fixtures/desktop.cjs')], env, cwd: folder });
    const page = await app.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    return page;
  };
  try {
    let page = await launch();
    await page.getByRole('button', { name: '设置', exact: true }).click();
    let dialog = page.getByRole('dialog', { name: '设置' });
    await expect(dialog.getByText('密钥仅从启动环境读取，不会在界面显示或保存。')).toBeVisible();
    await expect(dialog.getByRole('spinbutton', { name: '上下文窗口' })).toHaveAttribute('max', '2000000');
    await dialog.getByRole('combobox', { name: 'Embedding 运行方式' }).selectOption('local');
    await expect(dialog.getByRole('textbox', { name: 'Embedding Base URL' })).toHaveCount(0);
    await expect(dialog.getByText('使用本机已缓存的模型，无需填写远程连接。模型路径可通过启动环境指定。')).toBeVisible();
    await dialog.getByRole('combobox', { name: 'Embedding 运行方式' }).selectOption('remote');
    await expect(dialog.getByRole('textbox', { name: 'Embedding Base URL' })).toHaveAttribute('required', '');
    await dialog.getByRole('combobox', { name: 'Embedding 运行方式' }).selectOption('auto');
    await dialog.getByRole('textbox', { name: '聊天模型' }).fill('offline-fixture-model');
    await dialog.getByRole('spinbutton', { name: '上下文窗口' }).fill('8192');
    await dialog.getByRole('spinbutton', { name: '输出预留' }).fill('1024');
    await dialog.getByRole('checkbox', { name: '启用旧历史摘要' }).uncheck();
    await page.screenshot({ path: join(frontend, '../.local/harness-settings-window.png') });
    await dialog.getByRole('button', { name: '保存并应用' }).click();
    await expect(dialog.getByText('设置已应用。')).toBeVisible();
    const persisted = await readFile(join(folder, 'settings.json'), 'utf8');
    expect(JSON.parse(persisted)).toMatchObject({ chatModel: 'offline-fixture-model', contextWindow: 8192, outputReserve: 1024, summaryEnabled: false, embeddingProvider: 'auto' });
    expect(persisted).not.toContain('secret');
    expect(await page.evaluate(() => window.herta.getSettings())).not.toHaveProperty('apiKey');
    await dialog.getByRole('button', { name: '关闭设置' }).click();
    await page.getByRole('textbox', { name: '消息' }).fill('stream');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByText('正在生成，黑塔', { exact: true })).toBeVisible();
    const busy = await page.evaluate(async () => { try { await window.herta.applySettings(await window.herta.getSettings()); return ''; } catch (error) { return String(error); } });
    expect(busy).toContain('runs_active');
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await expect(dialog.getByRole('button', { name: '保存并应用' })).toBeDisabled();
    await dialog.getByRole('button', { name: '关闭设置' }).click();
    await writeFile(join(folder, 'stream-release'), '');
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();
    await page.getByText('上下文诊断 · 1 个步骤', { exact: true }).click();
    await expect(page.getByText('Persona hash', { exact: true })).toBeVisible();
    await expect(page.getByText('估算输入', { exact: true })).toBeVisible();
    await page.screenshot({ path: join(frontend, '../.local/harness-context-window.png') });
    await app!.close(); app = undefined;
    page = await launch();
    dialog = page.getByRole('dialog', { name: '设置' });
    await page.getByRole('button', { name: '设置', exact: true }).click();
    await expect(dialog.getByRole('textbox', { name: '聊天模型' })).toHaveValue('offline-fixture-model');
    await dialog.getByRole('button', { name: '关闭设置' }).click();
    await page.getByRole('navigation', { name: '历史会话' }).getByRole('button', { name: 'stream', exact: true }).click();
    await page.getByText('上下文诊断 · 1 个步骤', { exact: true }).click();
    await expect(page.getByText('Persona hash', { exact: true })).toBeVisible();
  } finally { if (app) await app.close(); await rm(folder, { recursive: true, force: true }); }
});

test('settings reports restart failure and missing configuration accurately through IPC', async () => {
  const frontend = resolve(import.meta.dirname, '../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta restart failure '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder, HERTA_FIXTURE_GATE: folder } as Record<string, string>;
  let app: ElectronApplication | undefined;
  try {
    app = await electron.launch({ args: [join(frontend, 'tests/fixtures/desktop.cjs')], env, cwd: folder });
    const page = await app.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    const original = await page.evaluate(() => window.herta.getSettings());
    await app.evaluate(({ app }, mainPath) => {
      const module = process.getBuiltinModule('module');
      const { backend } = module.createRequire(app.getAppPath() + '/package.json')(mainPath);
      const start = backend.start.bind(backend);
      let fail = true;
      backend.start = async () => { if (fail) { fail = false; backend.status = { state: 'unavailable', reason: 'start_failed' }; return; } await start(); };
    }, join(frontend, 'dist/electron/main.cjs'));
    await page.getByRole('button', { name: '设置', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '设置' });
    await dialog.getByRole('textbox', { name: '聊天模型' }).fill('restart-failure-model');
    await dialog.getByRole('button', { name: '保存并应用' }).click();
    await expect(dialog.getByText('服务启动失败，已恢复原设置。请检查本地环境后重试。')).toBeVisible();
    await expect(dialog.getByText('设置已应用。')).toHaveCount(0);
    expect(await page.evaluate(() => window.herta.getSettings())).toEqual(original);
    await expect(dialog.getByRole('textbox', { name: '聊天模型' })).toHaveValue(original.chatModel);
    await expect(page.getByRole('status')).toHaveText('服务就绪');
    await app.evaluate(({ app }, mainPath) => {
      const module = process.getBuiltinModule('module');
      const { backend } = module.createRequire(app.getAppPath() + '/package.json')(mainPath);
      backend.options.health = async () => ({ storage_writable: true, chat_available: false, rag_available: false, active_runs: 0 });
    }, join(frontend, 'dist/electron/main.cjs'));
    await dialog.getByRole('textbox', { name: '聊天模型' }).fill('');
    await dialog.getByRole('button', { name: '保存并应用' }).click();
    await expect(dialog.getByText('设置已保存，但聊天配置未就绪。请检查模型连接和启动环境中的密钥。')).toBeVisible();
    await expect(dialog.getByText('设置已应用。')).toHaveCount(0);
    await expect(page.getByRole('status')).toHaveText('配置未就绪');
  } finally { if (app) await app.close(); await rm(folder, { recursive: true, force: true }); }
});