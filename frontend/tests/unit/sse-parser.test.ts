import { expect, it } from 'vitest';
import { SSEParser } from '../../src/api/sse-parser';

it('decodes Chinese split at every byte and handles comments / CRLF frame boundaries', () => {
  const event = { schema_version: 1, type: 'llm.delta', run_id: 'r', session_id: 's', seq: 1, timestamp: '', payload: { text: '黑塔你好' } };
  const bytes = new TextEncoder().encode(': heartbeat\r\n\r\nevent: llm.delta\r\ndata: ' + JSON.stringify(event) + '\r\n\r\n');
  const parser = new SSEParser();
  const output = [...bytes].flatMap(byte => parser.push(new Uint8Array([byte])));
  expect(output).toEqual([event]);
});
