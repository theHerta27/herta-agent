import { expect, test } from '@playwright/test';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('closing the native window ends the dev process tree and permits reopening', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'Herta reopen '));
  await mkdir(join(folder, 'repo'));
  const frontend = resolve(import.meta.dirname, '../..');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !key.startsWith('HERTA_') && key !== 'ELECTRON_RUN_AS_NODE'));
  const ps = async (script: string) => (await promisify(execFile)('powershell.exe', ['-NoProfile', '-Command', script], { windowsHide: true })).stdout.trim();
  try {
    for (let cycle = 0; cycle < 2; cycle++) {
      const child = spawn(process.execPath, [join(frontend, 'scripts/dev.mjs')], {
        cwd: folder, env: { ...env, HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder, HERTA_CODING_REPO_ROOT: join(folder, 'repo') },
        windowsHide: true, stdio: 'pipe',
      });
      child.stdout.resume(); child.stderr.resume();
      const closed = new Promise(resolve => child.once('close', resolve));
      try {
        let main = 0;
        await expect.poll(async () => {
          main = Number(await ps(`Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq ${child.pid} -and $_.Name -eq 'electron.exe' } | Select-Object -ExpandProperty ProcessId`));
          return main ? await ps(`(Get-Process -Id ${main}).MainWindowHandle`) : '0';
        }, { timeout: 15000 }).not.toBe('0');
        await expect.poll(() => existsSync(join(folder, 'sessions.sqlite3'))).toBe(true);
        const owned = JSON.parse(await ps(`$all = Get-CimInstance Win32_Process; $ids = @(${main}); do { $next = @($all | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids } | Select-Object -ExpandProperty ProcessId); $ids += $next } while ($next.Count); ConvertTo-Json -Compress -InputObject @($ids)`)) as number[];
        await ps(`Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class HertaClose { [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l); }'; [HertaClose]::PostMessage((Get-Process -Id ${main}).MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)`);
        await expect.poll(() => child.exitCode, { timeout: 10000 }).toBe(0);
        await closed;
        for (const pid of owned) {
          await expect.poll(() => { try { process.kill(pid, 0); return true; } catch { return false; } }).toBe(false);
        }
      } finally {
        if (child.exitCode === null) child.kill();
        await closed;
      }
    }
  } finally {
    await expect(async () => rm(folder, { recursive: true, force: true })).toPass({ timeout: 10000 });
  }
});

test('single development command stays running until its parent closes', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'Herta dev 中文 '));
  await mkdir(join(folder, 'repo'));
  const frontend = resolve(import.meta.dirname, '../..');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    !key.startsWith('HERTA_') && key !== 'ELECTRON_RUN_AS_NODE'));
  const child = spawn(process.execPath, [join(frontend, 'scripts/dev.mjs')], {
    cwd: folder, env: { ...env, HERTA_SERVICE_PROVIDER: 'demo', HERTA_DESKTOP_DATA_DIR: folder, HERTA_CODING_REPO_ROOT: join(folder, 'repo') },
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
