import { afterEach, expect, test, vi } from 'vitest';
import { WorkspaceClient } from '../../electron/workspace';

afterEach(() => vi.unstubAllGlobals());

test('fixed workspace routes carry the main-process token and encode relative paths', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ entries: [] }) });
  vi.stubGlobal('fetch', fetcher);
  const client = new WorkspaceClient(() => 'http://127.0.0.1:8765', 'private-token');
  await client.list('root-id', '笔记/a&b.md');
  expect(fetcher.mock.calls[0][0]).toContain('path=%E7%AC%94%E8%AE%B0%2Fa%26b.md');
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer private-token');
  expect(fetcher.mock.calls[0][1].redirect).toBe('error');
});

test('invalid ids, oversized paths and nonboolean options never reach HTTP', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  const client = new WorkspaceClient(() => 'http://127.0.0.1:8765', 'private-token');
  await expect(client.list('../secret')).rejects.toThrow('invalid_request');
  await expect(client.read('root', 'a'.repeat(241))).rejects.toThrow('invalid_request');
  await expect(client.start('root', 'yes' as unknown as boolean)).rejects.toThrow('invalid_request');
  expect(fetcher).not.toHaveBeenCalled();
});

test('local server error remains a readable workbench failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: { message: '此路径受保护，无法读取。' } }) }));
  const client = new WorkspaceClient(() => 'http://127.0.0.1:8765', 'private-token');
  await expect(client.read('root', '.env')).rejects.toThrow('此路径受保护');
});
