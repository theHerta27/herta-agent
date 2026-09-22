import type { RunPacket, RunRequest, ServiceEvent } from '../shared/contracts';
import { SSEParser } from '../src/api/sse-parser';
import { BackendClient, identifier } from './backend-client';

interface RequestState { controller: AbortController; sessionId: string; runId?: string }

export class RunTransport {
  private requests = new Map<string, RequestState>();
  constructor(private client: BackendClient, private publish: (packet: RunPacket) => Promise<void>) {}
  get activeCount() { return this.requests.size; }
  start(request: RunRequest) {
    identifier(request.clientRequestId); identifier(request.sessionId);
    if (typeof request.text !== 'string' || !request.text.trim() || request.text.length > 10000) throw new Error('invalid_request');
    if (this.requests.has(request.clientRequestId)) throw new Error('duplicate_request');
    if ([...this.requests.values()].some(r => r.sessionId === request.sessionId)) throw new Error('http_409');
    if (this.requests.size >= 32) throw new Error('http_429');
    const endpoint = this.client.endpoint();
    const state: RequestState = { sessionId: request.sessionId, controller: new AbortController() };
    this.requests.set(request.clientRequestId, state);
    void this.consume(endpoint, request, state);
  }
  private async consume(endpoint: string, request: RunRequest, state: RequestState) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const response = await fetch(`${endpoint}/sessions/${request.sessionId}/runs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: request.text }),
        signal: state.controller.signal, redirect: 'error',
      });
      if (!response.ok) { await response.body?.cancel(); await this.publish({ clientRequestId: request.clientRequestId, rejected: response.status }); return; }
      if (!response.headers.get('content-type')?.startsWith('text/event-stream') || !response.body) throw new Error('invalid_stream');
      reader = response.body.getReader();
      const parser = new SSEParser();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        let batch: ServiceEvent[] = [];
        let size = 0;
        for (const event of parser.push(value)) {
          if (event.session_id !== request.sessionId || (state.runId && event.run_id !== state.runId)) throw new Error('invalid_run');
          state.runId = event.run_id;
          const bytes = Buffer.byteLength(JSON.stringify(event));
          if (bytes > 512 * 1024) throw new Error('event_too_large');
          if (batch.length && (batch.length >= 32 || size + bytes > 512 * 1024)) {
            await this.publish({ clientRequestId: request.clientRequestId, events: batch }); batch = []; size = 0;
          }
          batch.push(event); size += bytes;
        }
        if (batch.length) await this.publish({ clientRequestId: request.clientRequestId, events: batch });
      }
    } catch { /* EOF/transport failure must be reconciled from persistent facts. */ }
    finally {
      state.controller.abort();
      await reader?.cancel().catch(() => {});
      this.requests.delete(request.clientRequestId);
      await this.publish({ clientRequestId: request.clientRequestId, closed: true }).catch(() => {});
    }
  }
  async cancel(id: string) {
    identifier(id);
    const state = this.requests.get(id);
    if (!state) return;
    if (state.runId) await this.client.json(`/runs/${identifier(state.runId)}/cancel`, 'POST', {});
    else state.controller.abort();
  }
  dispose() { for (const state of this.requests.values()) state.controller.abort(); }
}
