import { spawn } from 'node:child_process';
import { mkdtemp, copyFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, expect, it } from 'vitest';
import { BackendProcess } from '../../electron/backend-process';

const root = resolve(import.meta.dirname, '../../..');
const python = join(root, '.venv/Scripts/python.exe');
let folder: string;
let backend: BackendProcess | undefined;
const environment = () => ({
  ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('HERTA_') && key !== 'WEB_CONCURRENCY')),
  HERTA_SERVICE_PROVIDER: 'demo',
});
const alive = (pid: number) => { try { process.kill(pid, 0); return true; } catch { return false; } };

afterEach(async () => {
  await backend?.stop();
  backend = undefined;
  if (folder) await rm(folder, { recursive: true, force: true });
});

it('stdio EOF shuts down the actual interpreter, without touching another Python process', async () => {
  folder = await mkdtemp(join(tmpdir(), 'Herta host 中文 '));
  const host = join(folder, '后端 host.py');
  await copyFile(join(root, 'frontend/desktop/backend_host.py'), host);
  const sentinel = spawn(python, ['-c', 'import sys; sys.stdin.read()'], { stdio: 'pipe', windowsHide: true });
  const child = spawn(python, ['-u', host, '--db', join(folder, 'sessions.sqlite3')], {
    env: environment(), cwd: folder, stdio: 'pipe', windowsHide: true,
  });
  const closed = new Promise(resolve => child.once('close', resolve));
  child.stderr.resume();
  try {
    const ready = await new Promise<{ pid: number; port: number }>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('host did not become ready')), 10000);
      let buffer = '';
      child.stdout.on('data', chunk => {
        buffer += chunk.toString();
        if (buffer.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(buffer.split('\n')[0])); }
      });
      child.on('error', reject);
    });
    expect(alive(ready.pid)).toBe(true);
    child.stdin.end(); // Parent pipe disappears, without an explicit shutdown command.
    await closed;
    expect(alive(ready.pid)).toBe(false);
    expect(sentinel.exitCode).toBeNull();
    // The same SQLite file is reusable immediately after EOF cleanup.
    backend = new BackendProcess({ python, host, root: folder, db: join(folder, 'sessions.sqlite3'), env: environment() });
    await backend.start();
    expect(backend.status.state).toBe('ready');
  } finally {
    child.stdin.end();
    await closed;
    const sentinelClosed = new Promise(resolve => sentinel.once('close', resolve));
    sentinel.stdin.end();
    await sentinelClosed;
  }
}, 20000);
