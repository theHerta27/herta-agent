import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { describe, expect, it, vi } from 'vitest';
import { BackendProcess } from '../../electron/backend-process';

function fixture() {
  const child = Object.assign(new EventEmitter(), {
    pid: 120, exitCode: null as number | null, stdin: new PassThrough(),
    stdout: new PassThrough(), stderr: new PassThrough(),
  });
  const spawn = vi.fn(() => child as unknown as ChildProcessWithoutNullStreams);
  const health = vi.fn(async () => ({
    storage_writable: true, chat_available: false, rag_available: false, active_runs: 0,
  }));
  const backend = new BackendProcess({
    python: 'D:\\中文 空格\\python.exe', host: 'D:\\中文 空格\\backend_host.py',
    root: 'D:\\中文 空格', db: 'D:\\中文 空格\\sessions.sqlite3',
    spawn, health, startupMs: 200, shutdownMs: 200,
  });
  const ready = () => child.stdout.write(JSON.stringify({ type: 'ready', protocol: 1, port: 12345, pid: 121 }) + '\n');
  const close = () => { child.exitCode = 0; child.emit('close', 0); };
  return { child, spawn, health, backend, ready, close };
}

describe('owned backend lifecycle', () => {
  it('waits for private ready and health before exposing an endpoint', async () => {
    const f = fixture();
    const starting = f.backend.start();
    expect(f.backend.status.state).toBe('starting');
    expect(f.backend.endpoint).toBeUndefined();
    expect(f.health).not.toHaveBeenCalled();
    f.ready();
    await starting;
    expect(f.health).toHaveBeenCalledWith('http://127.0.0.1:12345');
    expect(f.backend.status.state).toBe('needs_configuration');
    expect(f.backend.endpoint).toBe('http://127.0.0.1:12345');
    expect(f.spawn.mock.calls[0]).toBeDefined();
    f.close();
    expect(f.backend.status.state).toBe('unavailable');
    expect(f.backend.endpoint).toBeUndefined();
  });

  it('marks a configured offline service ready', async () => {
    const f = fixture();
    f.health.mockResolvedValue({ storage_writable: true, chat_available: true, rag_available: false, active_runs: 0 });
    const starting = f.backend.start();
    f.ready();
    await starting;
    expect(f.backend.status.state).toBe('ready');
    f.close();
  });

  it('reports missing interpreter without leaking OS error details', async () => {
    const f = fixture();
    const starting = f.backend.start();
    f.child.emit('error', new Error('ENOENT secret configuration'));
    f.close();
    await starting;
    expect(f.backend.status).toEqual({ state: 'unavailable', reason: 'start_failed' });
  });

  it('waits for process close after shutdown; closing during startup cannot become ready', async () => {
    const f = fixture();
    let commands = '';
    f.child.stdin.on('data', (data) => { commands += data.toString(); });
    const starting = f.backend.start();
    let finished = false;
    const stopping = f.backend.stop().then(() => { finished = true; });
    f.ready();
    await Promise.resolve();
    expect(finished).toBe(false);
    expect(commands).toContain('shutdown');
    f.close();
    await Promise.all([starting, stopping]);
    expect(f.backend.status.state).toBe('stopped');
    expect(f.backend.endpoint).toBeUndefined();
  });

  it('rejects malformed handshake and never probes arbitrary addresses', async () => {
    const f = fixture();
    const starting = f.backend.start();
    f.child.stdout.write('{"type":"ready","protocol":1,"port":-1,"pid":121}\n');
    f.close();
    await starting;
    expect(f.health).not.toHaveBeenCalled();
    expect(f.backend.endpoint).toBeUndefined();
  });

  it('does not publish stale ready when Python exits during the health request', async () => {
    const f = fixture();
    let resolveHealth!: (value: Awaited<ReturnType<typeof f.health>>) => void;
    f.health.mockImplementation(() => new Promise(resolve => { resolveHealth = resolve; }));
    const starting = f.backend.start();
    f.ready();
    await vi.waitFor(() => expect(f.health).toHaveBeenCalled());
    f.close();
    resolveHealth({ storage_writable: true, chat_available: true, rag_available: false, active_runs: 0 });
    await starting;
    expect(f.backend.status.state).toBe('unavailable');
    expect(f.backend.endpoint).toBeUndefined();
  });

  it('startup deadline closes its own process instead of leaving it running', async () => {
    const f = fixture();
    f.child.stdin.on('data', () => { queueMicrotask(f.close); });
    await f.backend.start();
    expect(f.backend.status).toEqual({ state: 'unavailable', reason: 'start_failed' });
    expect(f.child.exitCode).toBe(0);
  });

  it('allows closing again after a failed stop once the interpreter has exited', async () => {
    const f = fixture();
    const starting = f.backend.start();
    f.ready();
    await starting;
    // The launcher has exited but its interpreter still holds the stdio handles.
    f.child.exitCode = 0;
    await expect(f.backend.stop()).rejects.toThrow('stop_failed');
    f.close();
    await expect(f.backend.stop()).resolves.toBeUndefined();
    expect(f.backend.status.state).toBe('stopped');
  });
});
