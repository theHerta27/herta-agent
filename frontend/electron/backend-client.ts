import type { RunRecord, SessionPage, SessionRecord } from '../shared/contracts';

export interface Health {
  storage_writable: boolean;
  chat_available: boolean;
  rag_available: boolean;
  active_runs: number;
}

export function identifier(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-zA-Z0-9_-]{1,256}$/.test(value)) throw new Error('invalid_request');
  return value;
}
function pageSize(value: number) {
  if (!Number.isInteger(value) || value < 1 || value > 100) throw new Error('invalid_request');
  return value;
}

export class BackendClient {
  constructor(readonly endpoint: () => string) {}
  async json<T>(path: string, method = 'GET', body?: object): Promise<T> {
    const response = await fetch(this.endpoint() + path, {
      method, body: body ? JSON.stringify(body) : undefined,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      signal: AbortSignal.timeout(10000), redirect: 'error',
    });
    if (!response.ok) throw new Error(`http_${response.status}`);
    return response.json();
  }
  listSessions = (afterId?: string, limit = 50) => this.json<SessionRecord[]>(
    `/sessions?limit=${pageSize(limit)}${afterId ? '&after_id=' + identifier(afterId) : ''}`);
  createSession = () => this.json<SessionRecord>('/sessions', 'POST', {});
  getSession = (id: string, afterSeq = 0, limit = 100) => {
    if (!Number.isInteger(afterSeq) || afterSeq < 0) throw new Error('invalid_request');
    return this.json<SessionPage>(`/sessions/${identifier(id)}?after_seq=${afterSeq}&limit=${pageSize(limit)}`);
  };
  getRun = (id: string) => this.json<{ run: RunRecord; cancel_requested: boolean }>(`/runs/${identifier(id)}`);
}

export async function readHealth(endpoint: string): Promise<Health> {
  const response = await fetch(endpoint + '/health', { signal: AbortSignal.timeout(3000), redirect: 'error' });
  if (!response.ok) throw new Error('health_failed');
  const value = await response.json();
  if (typeof value.storage_writable !== 'boolean' || typeof value.chat_available !== 'boolean'
    || typeof value.rag_available !== 'boolean' || !Number.isInteger(value.active_runs)) {
    throw new Error('health_invalid');
  }
  return value;
}
