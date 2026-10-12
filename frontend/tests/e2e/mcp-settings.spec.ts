import { _electron as electron, expect, test } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('MCP native approval, readonly discovery, rollback and reopening use saved public config', async () => {
  const root = resolve(import.meta.dirname, '../../..'); const folder = await mkdtemp(join(tmpdir(), 'Herta MCP界面 '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('HERTA_') && k !== 'ELECTRON_RUN_AS_NODE')), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder };
  let app = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
  try {
    let page = await app.firstWindow(); await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    await page.getByRole('button', { name: '扩展', exact: true }).click();
    await page.getByRole('textbox', { name: 'MCP配置' }).fill('invalid json'); await page.getByRole('button', { name: '应用扩展' }).click();
    await expect(page.getByRole('button', { name: '应用扩展' })).toBeEnabled();
    const config = { servers: [{ name: 'sample', command: join(root, '.venv/Scripts/python.exe'), args: [join(root, 'examples/mcp/sample_server.py')], allowed_tools: ['herta_demo_status'], timeout: 10 }] };
    await page.getByRole('textbox', { name: 'MCP配置' }).fill(JSON.stringify(config));
    await app.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 0, checkboxChecked: false }); });
    await page.getByRole('button', { name: '应用扩展' }).click(); await expect(page.getByText('已取消，配置未保存。')).toBeVisible();
    expect((await page.evaluate(() => window.herta.mcp.get())).servers).toHaveLength(0);
    await app.evaluate(({ dialog }) => { dialog.showMessageBox = async () => ({ response: 1, checkboxChecked: false }); });
    await page.getByRole('button', { name: '应用扩展' }).click(); await expect(page.getByText('配置已保存，只读工具已连接。')).toBeVisible({ timeout: 20000 });
    const bad = { servers: [{ ...config.servers[0], args: [join(root, 'backend/tests/mcp_probe_server.py')], allowed_tools: ['probe_write'] }] };
    await page.getByRole('textbox', { name: 'MCP配置' }).fill(JSON.stringify(bad)); await page.getByRole('button', { name: '应用扩展' }).click();
    await expect(page.getByText(/已恢复先前配置/)).toBeVisible({ timeout: 20000 });
    expect((await page.evaluate(() => window.herta.mcp.get())).servers[0].allowed_tools).toEqual(['herta_demo_status']);
    await app.close(); app = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder }); page = await app.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    expect((await page.evaluate(() => window.herta.getBackendStatus())).mcpAvailable).toBe(true);
    await page.getByRole('button', { name: '扩展', exact: true }).click(); await page.getByRole('button', { name: '停用全部扩展' }).click();
    await expect(page.getByText('扩展已停用。')).toBeVisible({ timeout: 20000 });
  } finally { await app.close(); await rm(folder, { recursive: true, force: true }); }
});
