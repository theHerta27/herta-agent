import { expect, test } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('single development command stays running until its parent closes', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'Herta dev 中文 '));
  const frontend = resolve(import.meta.dirname, '../..');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !key.startsWith('HERTA_') && key !== 'ELECTRON_RUN_AS_NODE'));
  const child = spawn(process.execPath, [join(frontend, 'scripts/dev.mjs')], {
    cwd: folder, env: { ...env, HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder },
    windowsHide: true, stdio: 'pipe',
  });
  child.stdout.resume();
  child.stderr.resume();
  const closed = new Promise(resolve => child.once('close', resolve));
  try {
    await expect.poll(() => existsSync(join(folder, 'sessions.sqlite3')), { timeout: 10000 }).toBe(true);
    // Reproduces Windows Electron GUI stdin ending immediately after spawn.
    await new Promise(resolve => setTimeout(resolve, 3000));
    expect(child.exitCode).toBeNull();
  } finally {
    child.kill(); // Abrupt dev-runner exit must disconnect its owned Electron IPC.
    await closed;
    await expect(async () => {
      await rm(folder, { recursive: true, force: true });
    }).toPass({ timeout: 10000 });
  }
});
