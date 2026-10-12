import { afterEach, expect, test, vi } from 'vitest';
import { WorkspaceClient } from '../../electron/workspace';
import { makeFileOperations } from '../../src/state/file-operations';

afterEach(() => vi.unstubAllGlobals());

test('selected files produce explicit relative operations; none selected stays empty', () => {
  expect(makeFileOperations([], 'copy', '资料', '')).toEqual([]);
  expect(makeFileOperations(['a.md', 'sub/b.png'], 'organize', '', '')).toEqual([
    { kind: 'move', source: 'a.md', target: '文档/a.md' },
    { kind: 'move', source: 'sub/b.png', target: '图片/b.png' },
  ]);
  expect(makeFileOperations(['sub/a.md'], 'rename', '', 'new.md')).toEqual([{ kind: 'move', source: 'sub/a.md', target: 'sub/new.md' }]);
});

test('plan confirmation binds digest and request id on a fixed route', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'job' }) });
  vi.stubGlobal('fetch', fetcher);
  const client = new WorkspaceClient(() => 'http://127.0.0.1:8765', 'private-token');
  await client.confirm('plan', 'a'.repeat(64), 'request');
  expect(fetcher.mock.calls[0][0]).toBe('http://127.0.0.1:8765/workspace/plans/plan/confirm');
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ digest: 'a'.repeat(64), request_id: 'request' });
});

test('invalid file operations and digests do not reach HTTP', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  const client = new WorkspaceClient(() => 'http://127.0.0.1:8765', 'private-token');
  await expect(client.propose('root', [{ kind: 'delete', source: 'x', target: 'y' }] as never)).rejects.toThrow('invalid_request');
  await expect(client.confirm('plan', 'wrong', 'request')).rejects.toThrow('invalid_request');
  expect(fetcher).not.toHaveBeenCalled();
});
