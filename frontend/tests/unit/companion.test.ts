import { createServer } from 'node:http';
import { expect, it } from 'vitest';
import { BackendClient } from '../../electron/backend-client';
import { CompanionClient, actionRequest } from '../../electron/companion';

it('routes only known daily actions and checks bounds before any HTTP request', () => {
  expect(actionRequest({ kind: 'ack', id: 'delivery' })).toEqual({ path: '/companion/deliveries/delivery/ack', method: 'POST', body: {} });
  expect(() => actionRequest({ kind: 'snooze', id: 'reminder', minutes: 0 })).toThrow();
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
      response.end(JSON.stringify({ path: request.url, text: body.text, status: 'pending' }));
    });
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address() as { port: number };
    const client = new CompanionClient(new BackendClient(() => `http://127.0.0.1:${address.port}`));
    const result = await client.action({ kind: 'memory', text: '喜欢先看总结' });
    expect(result).toEqual({ path: '/companion/memories', text: '喜欢先看总结', status: 'pending' });
  } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
});
