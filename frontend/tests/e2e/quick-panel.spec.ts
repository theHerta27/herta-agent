import { _electron as electron, expect, test } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('quick panel shares one conversation and rejects stale input without a privileged bridge', async () => {
  const root = resolve(import.meta.dirname, '../../..'); const folder = await mkdtemp(join(tmpdir(), 'Herta 快捷 '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('HERTA_') && k !== 'ELECTRON_RUN_AS_NODE')), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder };
  const app = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
  try {
    const main = await app.firstWindow(); await expect(main.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    const opened = app.waitForEvent('window'); await main.evaluate(() => window.herta.quick.open()); const quick = await opened;
    expect(await quick.evaluate(() => ({ full: typeof window.herta, keys: Object.keys((window as unknown as { hertaQuick: object }).hertaQuick) }))).toEqual({ full: 'undefined', keys: ['state', 'onState', 'input', 'close', 'showMain'] });
    await quick.getByRole('textbox', { name: '快捷消息' }).fill('从快捷面板发起'); await quick.getByRole('button', { name: '发送', exact: true }).click();
    await expect.poll(async () => (await main.evaluate(() => window.herta.listSessions())).length).toBe(1);
    await expect(quick.getByText('与主窗口共用当前对话')).toBeVisible();
    const sessions = await main.evaluate(() => window.herta.listSessions()); const history = await main.evaluate(id => window.herta.getSession(id), sessions[0].session_id);
    expect(history.messages.some(m => m.message.role === 'user' && m.message.content === '从快捷面板发起')).toBe(true);
    await quick.getByRole('textbox', { name: '快捷消息' }).fill('尚未提交的旧输入');
    await main.getByRole('textbox', { name: '消息' }).fill('主窗口的新草稿');
    await quick.getByRole('button', { name: '保存到主窗口草稿' }).click();
    await expect(quick.getByRole('alert')).toContainText('已变化'); await expect(main.getByRole('textbox', { name: '消息' })).toHaveValue('主窗口的新草稿');
    await quick.screenshot({ path: join(root, '.local/quick-panel-desktop.png') });
  } finally { await app.close(); await rm(folder, { recursive: true, force: true }); }
});
