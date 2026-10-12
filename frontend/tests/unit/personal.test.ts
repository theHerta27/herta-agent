import { expect, it, vi } from 'vitest';
import { PersonalClient } from '../../electron/personal';
import { CompanionClient } from '../../electron/companion';
import type { BackendClient } from '../../electron/backend-client';

it('personalization only uses the private fixed endpoint and rejects arbitrary commands', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal('fetch', fetcher);
  const client = new PersonalClient(() => 'http://127.0.0.1:123', 'private');
  await client.action({ kind: 'persona', revision: 1, text: '说得简短些' });
  expect(fetcher.mock.calls[0][0]).toBe('http://127.0.0.1:123/personal');
  await expect(client.action({ kind: 'shell' } as never)).rejects.toThrow();
  expect(fetcher).toHaveBeenCalledTimes(1); vi.unstubAllGlobals();
});
it('voice cancellation waits for the owned worker to finish before changing providers', async () => {
  const json = vi.fn().mockResolvedValueOnce({ active_workers: 1 }).mockResolvedValue({ active_workers: 0 });
  const voice = new CompanionClient({ json } as unknown as BackendClient);
  await voice.cancelAndWait(); expect(json).toHaveBeenCalledTimes(2);
});
