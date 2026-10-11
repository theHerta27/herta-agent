import { createServer } from 'node:http';
import { expect, it } from 'vitest';
import { BackendClient } from '../../electron/backend-client';
import { CompanionClient, actionRequest } from '../../electron/companion';

it('routes only known daily actions and checks bounds before any HTTP request', () => {
  expect(actionRequest({ kind: 'music', action: 'pause' })).toEqual({ path: '/companion/music/control', method: 'POST', body: { action: 'pause' } });
  expect(() => actionRequest({ kind: 'music', action: 'volume', volume: 101 })).toThrow();
  expect(() => actionRequest({ kind: 'delete', path: 'C:/secret' })).toThrow();
  expect(() => actionRequest({ kind: 'cancel_reminder', id: '../outside' })).toThrow();
});

it('daily action result comes from the actual local HTTP service', async () => {
  const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', chunk => chunks.push(chunk));
    request.on('end', () => {
      response.setHeader('Content-Type', 'application/json');
      const body = JSON.parse(Buffer.concat(chunks).toString());
      response.end(JSON.stringify({ path: request.url, action: body.action, revision: 4 }));
    });
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address() as { port: number };
    const client = new CompanionClient(new BackendClient(() => `http://127.0.0.1:${address.port}`));
    const result = await client.action({ kind: 'music', action: 'pause' });
    expect(result).toEqual({ path: '/companion/music/control', action: 'pause', revision: 4 });
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});
