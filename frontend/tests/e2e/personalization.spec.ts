import { _electron as electron, expect, test } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('personality, voice preferences and reviewed skills persist without increasing tool permissions', async () => {
  const root = resolve(import.meta.dirname, '../../..'); const folder = await mkdtemp(join(tmpdir(), 'Herta 个性化 '));
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('HERTA_') && k !== 'ELECTRON_RUN_AS_NODE')), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder };
  let desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
  try {
    const page = await desktop.firstWindow(); await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    await page.getByRole('button', { name: '个性', exact: true }).click();
    const modal = page.getByRole('dialog');
    await expect.poll(() => modal.evaluate(el => ({ modal: el.matches(':modal'), fits: el.getBoundingClientRect().right <= innerWidth && el.getBoundingClientRect().left >= 0 }))).toEqual({ modal: true, fits: true });
    await page.getByRole('textbox', { name: '人格补充' }).fill('先回答，再解释。'); await page.getByRole('button', { name: '保存人格' }).click();
    await expect(page.getByText('已保存人格')).toBeVisible();
    await page.getByRole('textbox', { name: 'Skill名称' }).fill('复习方法');
    await page.getByRole('textbox', { name: 'Skill步骤' }).fill('先自测，再查漏补缺。');
    await page.getByRole('button', { name: '保存待审核草案' }).click();
    await expect(page.locator('.personal-skill')).toContainText('待审核');
    await page.locator('.personal-skill').getByRole('button', { name: '审核并启用' }).click();
    await expect(page.locator('.personal-skill')).toContainText('已启用');
    await page.locator('.personal-skill').getByRole('button', { name: '停用', exact: true }).click();
    await expect(page.locator('.personal-skill')).toContainText('已停用');
    await page.getByRole('combobox', { name: '朗读音色' }).selectOption('the_herta');
    await page.getByRole('button', { name: '保存音色' }).click();
    await expect(page.getByText('已保存音色')).toBeVisible();
    const saved = await page.evaluate(() => window.herta.personal.snapshot());
    expect(saved.voice.provider).toBe('the_herta'); expect(saved.skills[0].enabled).toBe(false);
    await page.screenshot({ path: join(root, '.local/personalization-desktop.png') });
    await desktop.close();
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const reopened = await desktop.firstWindow();
    await expect(reopened.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    const persisted = await reopened.evaluate(() => window.herta.personal.snapshot());
    expect(persisted.persona.text).toBe('先回答，再解释。');
    expect(persisted.skills[0].enabled).toBe(false); expect(persisted.voice.provider).toBe('the_herta');
  } finally { await desktop.close(); await rm(folder, { recursive: true, force: true }); }
});
