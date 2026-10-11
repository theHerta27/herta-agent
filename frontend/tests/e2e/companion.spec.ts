import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { access, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('daily bridge persists reminders and preferences; close hides and explicit quit cleans backend', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 陪伴 '));
  let desktop: ElectronApplication | undefined;
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder } as Record<string, string>;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const page = await desktop.firstWindow();
    page.on('pageerror', error => console.error('renderer:', error.message));
    await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    const first = await page.evaluate(() => window.herta.companion.snapshot());
    await page.evaluate(prefs => window.herta.companion.action({ kind: 'preferences', value: { ...prefs, nickname: '开拓者', volume: 25 } }), first.preferences);
    await page.evaluate(() => window.herta.companion.action({ kind: 'create_reminder', title: '休息', due_at: new Date(Date.now() + 60000).toISOString(), repeat: 'once' }));
    const snapshot = await page.evaluate(() => window.herta.companion.snapshot());
    expect(snapshot.preferences.volume).toBe(25);
    expect(snapshot.reminders[0].title).toBe('休息');
    const wav = Buffer.alloc(32044); wav.write('RIFF'); wav.writeUInt32LE(32036, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(32000, 40);
    const music = join(folder, '本地音乐.wav'); await writeFile(music, wav);
    await desktop.evaluate(({ dialog }, file) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [file] }); }, music);
    const imported = await page.evaluate(() => window.herta.companion.importMusic());
    expect(imported[0].title).toBe('本地音乐');
    const audio = await page.evaluate(async id => {
      const response = await fetch(`herta-media://music/${id}`);
      return { status: response.status, size: (await response.arrayBuffer()).byteLength };
    }, imported[0].id);
    expect(audio).toEqual({ status: 200, size: 32044 });
    await page.getByRole('button', { name: '日常', exact: true }).click();
    await expect(page.getByRole('heading', { name: '日常', exact: true })).toBeVisible();
    await page.evaluate(() => window.herta.companion.action({ kind: 'music', action: 'volume', volume: 20 }));
    await expect(page.getByRole('slider', { name: '默认音量' })).toHaveValue('20');
    await page.getByRole('textbox', { name: '提醒内容' }).fill('起来走走');
    await page.getByRole('button', { name: '添加提醒', exact: true }).click();
    await expect(page.locator('.reminder-item').filter({ hasText: '起来走走' })).toBeVisible();
    await page.locator('.reminder-item').filter({ hasText: '起来走走' }).getByRole('button', { name: '取消' }).click();
    await expect(page.locator('.reminder-item').filter({ hasText: '起来走走' })).toContainText('已停用');
    await page.getByRole('textbox', { name: '记住一件事' }).fill('学习时喜欢安静的音乐');
    await page.getByRole('button', { name: '添加记忆' }).click();
    await page.locator('.memory-item').filter({ hasText: '学习时喜欢安静的音乐' }).getByRole('button', { name: '保存' }).click();
    await expect(page.locator('.memory-item').filter({ hasText: '学习时喜欢安静的音乐' })).toContainText('已保存');
    await page.getByRole('button', { name: '播放本地音乐', exact: true }).click();
    await expect.poll(async () => (await page.evaluate(() => window.herta.companion.snapshot())).playback.actual).toBe('playing');
    await page.getByRole('button', { name: '暂停音乐', exact: true }).click();
    await expect.poll(async () => (await page.evaluate(() => window.herta.companion.snapshot())).playback.actual).toBe('paused');
    await page.evaluate(async () => {
      const snapshot = await window.herta.companion.snapshot();
      await window.herta.companion.action({ kind: 'preferences', value: { ...snapshot.preferences, quiet_start: 0, quiet_end: 0 } });
      await window.herta.companion.action({ kind: 'create_reminder', title: '到期测试', due_at: new Date(Date.now() + 1500).toISOString(), repeat: 'once' });
    });
    await expect(page.locator('.delivery-item').filter({ hasText: '到期测试' })).toBeVisible();
    await page.locator('.delivery-item').filter({ hasText: '到期测试' }).getByRole('button', { name: '10分钟后' }).click();
    await expect(page.locator('.delivery-item').filter({ hasText: '到期测试' })).toHaveCount(0);
    await page.getByRole('button', { name: '开始专注' }).click();
    await expect(page.locator('.reminder-item').filter({ hasText: '专注结束' })).toBeVisible();
    await desktop.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].close(); });
    expect(await desktop.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isVisible())).toBe(false);
    expect((await page.evaluate(() => window.herta.getBackendStatus())).state).toBe('ready');
    await desktop.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].show(); });
    await desktop.close(); desktop = undefined;
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const reopened = await desktop.firstWindow();
    await expect(reopened.getByRole('status')).toHaveText('服务就绪');
    expect((await reopened.evaluate(() => window.herta.companion.snapshot())).preferences.nickname).toBe('开拓者');
    await reopened.getByRole('button', { name: '日常', exact: true }).click();
    await reopened.getByRole('button', { name: '重置偏好' }).click();
    await expect(reopened.getByRole('textbox', { name: '称呼' })).toHaveValue('');
    await expect(reopened.getByRole('slider', { name: '默认音量' })).toHaveValue('40');
    await reopened.screenshot({ path: join(root, '.local/companion-daily-desktop.png') });
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});

test('local microphone fixture fills an editable draft; speaking and session cancellation use the real desktop', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const capture = join(root, '.local/companion-voice-smoke.wav');
  try { await access(capture); } catch { test.skip(true, 'optional local voice fixture has not been prepared'); }
  const folder = await mkdtemp(join(tmpdir(), 'Herta 本地语音 '));
  let desktop: ElectronApplication | undefined;
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder } as Record<string, string>;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend'), '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=' + capture], env, cwd: folder });
    const page = await desktop.firstWindow();
    page.on('pageerror', error => console.error('renderer:', error.message));
    await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    const voice = await page.evaluate(() => window.herta.companion.voiceStatus());
    test.skip(!voice.tts || !voice.asr, 'local voice models are optional');
    await expect(page.getByRole('button', { name: '录音', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '录音', exact: true }).click();
    await expect(page.getByRole('button', { name: '结束录音' })).toBeVisible();
    await page.waitForTimeout(3500); // Capture actual audio frames from the public local fixture.
    await page.getByRole('button', { name: '结束录音' }).click();
    await page.getByRole('textbox', { name: '消息' }).fill('我想问：');
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue(/我想问：[\s\S]+黑塔/, { timeout: 20000 });
    await page.getByRole('textbox', { name: '消息' }).fill('本地语音验收');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '朗读', exact: true }).last()).toBeEnabled();
    await page.evaluate(() => {
      const original = window.Audio;
      const probe = window as typeof window & { speechDevices: HTMLAudioElement[] };
      probe.speechDevices = [];
      window.Audio = new Proxy(original, { construct(target, args) {
        const audio = Reflect.construct(target, args) as HTMLAudioElement;
        probe.speechDevices.push(audio);
        audio.addEventListener('playing', () => { document.documentElement.dataset.voicePlayed = 'yes'; });
        return audio;
      } });
    });
    await page.getByRole('button', { name: '朗读', exact: true }).last().click();
    await expect.poll(() => page.evaluate(() => document.documentElement.dataset.voicePlayed), { timeout: 20000 }).toBe('yes');
    await page.getByRole('button', { name: '停止声音' }).click();
    await expect(page.getByRole('button', { name: '朗读', exact: true }).last()).toBeVisible();
    await page.evaluate(async () => {
      delete document.documentElement.dataset.voicePlayed;
      const snapshot = await window.herta.companion.snapshot();
      await window.herta.companion.action({ kind: 'preferences', value: { ...snapshot.preferences, auto_read: true } });
    });
    await expect.poll(async () => (await page.evaluate(() => window.herta.companion.snapshot())).preferences.auto_read).toBe(true);
    await page.waitForTimeout(800); // Allow the normal renderer preference poll before sending.
    await page.getByRole('textbox', { name: '消息' }).fill('黑塔，休息了。'.repeat(90));
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect.poll(() => page.evaluate(() => document.documentElement.dataset.voicePlayed), { timeout: 20000 }).toBe('yes');
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await expect.poll(() => page.evaluate(() => (window as typeof window & { speechDevices: HTMLAudioElement[] }).speechDevices.every(audio => audio.paused))).toBe(true);
    await page.getByRole('textbox', { name: '消息' }).fill('阻止过期识别');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '录音', exact: true })).toBeEnabled();
    await page.evaluate(() => {
      const close = AudioContext.prototype.close;
      AudioContext.prototype.close = function () {
        AudioContext.prototype.close = close;
        const closing = close.call(this);
        return new Promise<void>(resolve => { (window as typeof window & { releaseClose: () => Promise<void> }).releaseClose = async () => { await closing; resolve(); }; });
      };
    });
    await desktop.evaluate(() => {
      const probe = globalThis as typeof globalThis & { asrRequests: number }; probe.asrRequests = 0;
      const request = globalThis.fetch;
      globalThis.fetch = (...args: Parameters<typeof fetch>) => { if (String(args[0]).endsWith('/companion/speech/asr')) probe.asrRequests++; return request(...args); };
    });
    await page.getByRole('button', { name: '录音', exact: true }).click();
    await expect(page.getByRole('button', { name: '结束录音' })).toBeVisible();
    await page.waitForTimeout(3000);
    await page.getByRole('button', { name: '结束录音' }).click();
    await expect.poll(() => page.evaluate(() => typeof (window as typeof window & { releaseClose?: () => Promise<void> }).releaseClose)).toBe('function');
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await page.evaluate(() => (window as typeof window & { releaseClose: () => Promise<void> }).releaseClose());
    await expect(page.getByRole('button', { name: '录音', exact: true })).toBeVisible();
    await page.waitForTimeout(2500);
    await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue('');
    expect(await desktop.evaluate(() => (globalThis as typeof globalThis & { asrRequests: number }).asrRequests)).toBe(0);
    await page.screenshot({ path: join(root, '.local/companion-voice-desktop.png') });
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});

test('local reading failures provide visible retry feedback', async () => {
  const root = resolve(import.meta.dirname, '../../..');
  const folder = await mkdtemp(join(tmpdir(), 'Herta 语音错误 '));
  let desktop: ElectronApplication | undefined;
  const env = { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && !['ELECTRON_RUN_AS_NODE', 'WEB_CONCURRENCY'].includes(key))), HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder } as Record<string, string>;
  try {
    desktop = await electron.launch({ args: [join(root, 'frontend')], env, cwd: folder });
    const page = await desktop.firstWindow();
    await expect(page.getByRole('status')).toHaveText('服务就绪', { timeout: 20000 });
    test.skip(!(await page.evaluate(() => window.herta.companion.voiceStatus())).tts, 'local voice model is optional');
    await page.getByRole('textbox', { name: '消息' }).fill('本地失败反馈');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByRole('button', { name: '朗读', exact: true }).last()).toBeEnabled();
    await desktop.evaluate(() => {
      const request = globalThis.fetch;
      globalThis.fetch = (...args: Parameters<typeof fetch>) => String(args[0]).endsWith('/companion/speech/tts') ? Promise.resolve(new Response('{}', { status: 503 })) : request(...args);
    });
    await page.getByRole('button', { name: '朗读', exact: true }).last().click();
    await expect(page.getByRole('alert')).toContainText('本地朗读失败');
    await expect(page.getByRole('button', { name: '朗读', exact: true }).last()).toBeEnabled();
  } finally { await desktop?.close(); await rm(folder, { recursive: true, force: true }); }
});
