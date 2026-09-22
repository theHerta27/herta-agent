import { afterEach, expect, it, vi } from 'vitest';
import { BackendClient } from '../../electron/backend-client';
import { RunTransport } from '../../electron/run-transport';
import type { RunPacket } from '../../shared/contracts';

afterEach(() => vi.unstubAllGlobals());
it('returns HTTP rejection separately, posts only text, and never retries', async () => {
  const fetch = vi.fn(async () => new Response('{}', { status: 429 }));
  vi.stubGlobal('fetch', fetch);
  const packets: RunPacket[] = [];
  const transport = new RunTransport(new BackendClient(() => 'http://127.0.0.1:1'), async packet => { packets.push(packet); });
  transport.start({ clientRequestId: 'q', sessionId: 's', text: 'hello' });
  await vi.waitFor(() => expect(packets.at(-1)?.closed).toBe(true));
  expect(packets[0].rejected).toBe(429);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]).toEqual(['http://127.0.0.1:1/sessions/s/runs', expect.objectContaining({ body: '{"text":"hello"}' })]);
});

it('Stop before the first event aborts the owned POST and reports closure', async () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal('fetch', (_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
    signal = options.signal as AbortSignal;
    signal.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  const packets: RunPacket[] = [];
  const transport = new RunTransport(new BackendClient(() => 'http://127.0.0.1:1'), async packet => { packets.push(packet); });
  transport.start({ clientRequestId: 'q', sessionId: 's', text: 'hello' });
  await transport.cancel('q');
  await vi.waitFor(() => expect(packets.at(-1)?.closed).toBe(true));
  expect(signal?.aborted).toBe(true);
  expect(packets.some(p => p.events?.some(e => e.type === 'run.completed'))).toBe(false);
});
