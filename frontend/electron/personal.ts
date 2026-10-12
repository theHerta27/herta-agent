import type { PersonalAction, PersonalSnapshot } from '../shared/personal-contracts';
export class PersonalClient {
  constructor(private endpoint: () => string, private token: string) {}
  private async request<T>(method: string, body?: object): Promise<T> {
    const response = await fetch(this.endpoint() + '/personal', { method, headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(10000), redirect: 'error' });
    const result = await response.json(); if (!response.ok) throw new Error(result?.error?.message ?? '记录已变化或参数无效，请刷新。'); return result;
  }
  snapshot = () => this.request<PersonalSnapshot>('GET');
  async action(value: PersonalAction): Promise<unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value) || !['persona', 'voice', 'memory', 'skill', 'draft', 'from_task'].includes(value.kind) || JSON.stringify(value).length > 40000 || Object.keys(value).some(k => !['kind', 'id', 'revision', 'action', 'text', 'title', 'provider', 'emotion'].includes(k))) throw new Error('invalid_request');
    return this.request('POST', value);
  }
}
