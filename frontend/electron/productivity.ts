import { identifier } from './backend-client';
import type { ProductivityAction, ProductivitySnapshot } from '../shared/productivity-contracts';
import type { DocumentPreview } from '../shared/workspace-contracts';

export class ProductivityClient {
  constructor(private endpoint: () => string, private token: string) {}
  private async request<T>(route: string, method = 'GET', body?: object, timeout = 10000): Promise<T> {
    const response = await fetch(this.endpoint() + '/productivity' + route, { method, headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(timeout), redirect: 'error' });
    const value = await response.json();
    if (!response.ok) throw new Error(value?.error?.message ?? '操作未完成，请刷新后检查时间或记录。');
    return value;
  }
  snapshot = () => this.request<ProductivitySnapshot>('');
  material = async (id: string) => this.request<DocumentPreview>(`/materials/${identifier(id)}/document`, 'GET', undefined, 50000);
  history = async (id: string) => this.request<{ action: string; due_at: string | null; created_at: string }[]>(`/tasks/${identifier(id)}/history`);
  async action(input: ProductivityAction): Promise<unknown> {
    if (!input || typeof input !== 'object' || Array.isArray(input) || !input.value || typeof input.value !== 'object' || Array.isArray(input.value) || JSON.stringify(input).length > 26000 || Object.keys(input).some(key => !['kind', 'value', 'id'].includes(key))) throw new Error('invalid_request');
    switch (input.kind) {
      case 'create_task': return this.request('/tasks', 'POST', input.value);
      case 'task': return this.request(`/tasks/${identifier(input.id)}`, 'POST', input.value);
      case 'create_goal': return this.request('/goals', 'POST', input.value);
      case 'goal': return this.request(`/goals/${identifier(input.id)}`, 'POST', input.value);
      case 'material': return this.request('/materials', 'POST', input.value);
      case 'material_progress': return this.request(`/materials/${identifier(input.id)}`, 'POST', input.value);
      case 'review': return this.request(`/materials/${identifier(input.id)}/review`, 'POST', input.value);
      case 'role': return this.request('/role', 'POST', input.value);
      case 'recitation': return this.request('/recitation', 'POST', input.value);
      default: throw new Error('invalid_request');
    }
  }
}
