import { spawn as spawnChild, execFile, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { readHealth, type Health } from './backend-client';
import type { BackendStatus } from '../shared/contracts';

interface Options {
  python: string; host: string; root: string; db: string;
  env?: NodeJS.ProcessEnv;
  spawn?: (file: string, args: string[], options: object) => ChildProcessWithoutNullStreams;
  health?: (endpoint: string) => Promise<Health>;
  startupMs?: number; shutdownMs?: number;
}

function deadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('deadline')), ms);
    promise.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}

/** Owns one launcher and its stdio-connected interpreter, never a discovered service. */
export class BackendProcess {
  status: BackendStatus = { state: 'stopped' };
  endpoint: string | undefined;
  pid: number | undefined;
  launcherPid: number | undefined;
  private child?: ChildProcessWithoutNullStreams;
  private closed = Promise.resolve();
  private stopping?: Promise<void>;
  private isClosed = false;
  private listeners = new Set<(status: BackendStatus) => void>();

  constructor(private options: Options) {}

  configureEnvironment(env: NodeJS.ProcessEnv) {
    if (this.child || this.status.state !== 'stopped') throw new Error('backend_busy');
    this.options.env = { ...env };
  }

  subscribe(handler: (status: BackendStatus) => void) {
    this.listeners.add(handler);
    return () => { this.listeners.delete(handler); };
  }

  private publish(status: BackendStatus) {
    this.status = status;
    for (const listener of this.listeners) listener(status);
  }

  async start() {
    if (this.child || this.status.state !== 'stopped') return;
    this.isClosed = false;
    this.publish({ state: 'starting' });
    try {
      const spawn = this.options.spawn ?? spawnChild;
      const child = spawn(this.options.python, ['-u', this.options.host, '--db', this.options.db], {
        cwd: this.options.root, env: this.options.env ?? process.env,
        shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
      });
      this.child = child;
      this.launcherPid = child.pid;
      this.closed = new Promise(resolve => child.once('close', () => {
        this.isClosed = true;
        this.endpoint = undefined;
        if (!this.stopping && this.status.state !== 'unavailable') {
          this.publish({ state: 'unavailable', reason: 'process_exited' });
        }
        resolve();
      }));
      // Never forward raw process output or environment to the renderer/logs.
      child.stderr.resume();
      child.stdin.on('error', () => {});
      const ready = new Promise<{ port: number; pid: number }>((resolve, reject) => {
        let buffer = '';
        const data = (chunk: Buffer) => {
          buffer += chunk.toString('utf8');
          if (buffer.length > 4096) { reject(new Error('handshake_invalid')); return; }
          if (!buffer.includes('\n')) return;
          child.stdout.removeListener('data', data);
          child.stdout.resume();
          try {
            const value = JSON.parse(buffer.slice(0, buffer.indexOf('\n')));
            if (value.type !== 'ready' || value.protocol !== 1 || !Number.isInteger(value.port)
              || value.port < 1 || value.port > 65535 || !Number.isInteger(value.pid) || value.pid < 1) {
              throw new Error('handshake_invalid');
            }
            resolve(value);
          } catch { reject(new Error('handshake_invalid')); }
        };
        child.stdout.on('data', data);
        child.on('error', () => reject(new Error('start_failed')));
        child.once('close', () => reject(new Error('process_exited')));
      });
      const value = await deadline(ready, this.options.startupMs ?? 60000);
      this.pid = value.pid;
      if (this.stopping || this.isClosed) return;
      const endpoint = `http://127.0.0.1:${value.port}`;
      const health = await (this.options.health ?? readHealth)(endpoint);
      if (this.stopping || this.isClosed) return;
      if (!health.storage_writable) throw new Error('storage_unavailable');
      this.endpoint = endpoint;
      this.publish({
        state: health.chat_available ? 'ready' : 'needs_configuration', ragAvailable: health.rag_available,
        embeddingProvider: typeof health.embedding_provider === 'string' ? health.embedding_provider.slice(0, 512) : undefined,
        embeddingModel: typeof health.embedding_model === 'string' ? health.embedding_model.slice(0, 512) : undefined,
        mcpAvailable: health.mcp_available === true,
        mcpError: typeof health.mcp_error === 'string' ? health.mcp_error.slice(0, 512) : undefined,
      });
    } catch {
      if (this.stopping) return;
      this.publish({ state: 'unavailable', reason: 'start_failed' });
      try { await this.stop(); } catch { /* stop already reports safe failure */ }
      this.publish({ state: 'unavailable', reason: 'start_failed' });
    }
  }

  stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    if (!this.child && this.status.state === 'stopped') return Promise.resolve();
    this.endpoint = undefined;
    this.publish({ state: 'stopping' });
    this.stopping = this.closeOwned().finally(() => { this.stopping = undefined; });
    return this.stopping;
  }

  private async closeOwned() {
    const child = this.child;
    if (child && !this.isClosed) {
      child.stdin.end('{"type":"shutdown","protocol":1}\n');
      try {
        await deadline(this.closed, this.options.shutdownMs ?? 20000);
      } catch {
        // The retained, still-running launcher owns the interpreter tree on Windows.
        // Never kill by executable name or a PID rediscovered from a port.
        try {
          if (child.exitCode !== null || !child.pid) throw new Error('owner_exited');
          await promisify(execFile)(join(process.env.SystemRoot ?? 'C:\\Windows', 'System32/taskkill.exe'),
            ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, timeout: 5000 });
          await deadline(this.closed, 5000);
        } catch {
          this.publish({ state: 'unavailable', reason: 'stop_failed' });
          throw new Error('stop_failed');
        }
      }
    }
    this.child = undefined;
    this.pid = undefined;
    this.launcherPid = undefined;
    this.publish({ state: 'stopped' });
  }
}
