import type { AnalysisJob, FileListing, TextPreview, WorkspaceRoot } from '../shared/workspace-contracts';
import { identifier } from './backend-client';

function bounded(value: unknown, max: number) {
  if (typeof value !== 'string' || value.length > max) throw new Error('invalid_request');
  return value;
}
function boolean(value: unknown) {
  if (typeof value !== 'boolean') throw new Error('invalid_request');
  return value;
}

/** Only the Electron main process receives this client and its grant token. */
export class WorkspaceClient {
  constructor(private endpoint: () => string, private token: string) {}
  private async request<T>(route: string, method = 'GET', body?: object): Promise<T> {
    const response = await fetch(this.endpoint() + '/workspace' + route, {
      method, headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(10000), redirect: 'error',
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value?.error?.message ?? '文件工作台暂不可用。');
    return value;
  }
  roots = () => this.request<WorkspaceRoot[]>('/roots');
  grant = (path: string) => this.request<WorkspaceRoot>('/roots', 'POST', { path: bounded(path, 240) });
  share = async (id: string, enabled: boolean) => this.request<WorkspaceRoot>(`/roots/${identifier(id)}/sharing`, 'POST', { enabled: boolean(enabled) });
  revoke = async (id: string) => { await this.request(`/roots/${identifier(id)}`, 'DELETE'); };
  list = async (id: string, path = '') => this.request<FileListing>(`/roots/${identifier(id)}/files?path=${encodeURIComponent(bounded(path, 240))}`);
  search = async (id: string, query: string) => this.request<FileListing>(`/roots/${identifier(id)}/search?query=${encodeURIComponent(bounded(query, 80))}`);
  read = async (id: string, path: string) => this.request<TextPreview>(`/roots/${identifier(id)}/text?path=${encodeURIComponent(bounded(path, 240))}`);
  jobs = async (id: string) => this.request<AnalysisJob[]>(`/roots/${identifier(id)}/jobs`);
  start = async (id: string, duplicates: boolean) => this.request<AnalysisJob>(`/roots/${identifier(id)}/jobs`, 'POST', { duplicates: boolean(duplicates) });
  cancel = async (id: string) => { await this.request(`/jobs/${identifier(id)}/cancel`, 'POST', {}); };
}
