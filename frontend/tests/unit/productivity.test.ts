import { afterEach, expect, test, vi } from 'vitest';
import { ProductivityClient } from '../../electron/productivity';

afterEach(() => vi.unstubAllGlobals());

test('task changes use a fixed authenticated route with explicit version', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'completed' }) });
  vi.stubGlobal('fetch', fetcher);
  const client = new ProductivityClient(() => 'http://127.0.0.1:8765', 'control-token');
  await client.action({ kind: 'task', id: 'task-id', value: { action: 'complete', revision: 3 } });
  expect(fetcher.mock.calls[0][0]).toBe('http://127.0.0.1:8765/productivity/tasks/task-id');
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer control-token');
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ action: 'complete', revision: 3 });
});

test('unknown operations and traversal ids never reach HTTP', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  const client = new ProductivityClient(() => 'http://127.0.0.1:8765', 'control-token');
  await expect(client.action({ kind: 'execute', url: 'http://outside' } as never)).rejects.toThrow('invalid_request');
  await expect(client.material('../private')).rejects.toThrow('invalid_request');
  expect(fetcher).not.toHaveBeenCalled();
});
