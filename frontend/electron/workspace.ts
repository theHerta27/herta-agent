import type { AnalysisJob, FileListing, TextPreview, WorkspaceRoot, FileOperation, FilePlan, FileJob, DocumentPreview, KnowledgeResults, DocumentTransform } from '../shared/workspace-contracts';
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
  private async request<T>(route: string, method = 'GET', body?: object, timeout = 10000): Promise<T> {
    const response = await fetch(this.endpoint() + '/workspace' + route, {
      method, headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(timeout), redirect: 'error',
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
  propose = async (id: string, operations: FileOperation[]) => {
    if (!Array.isArray(operations) || !operations.length || operations.length > 100 || operations.some(op => !op || !['copy', 'move', 'mkdir'].includes(op.kind) || typeof op.target !== 'string' || op.target.length > 240 || (op.source !== undefined && typeof op.source !== 'string'))) throw new Error('invalid_request');
    return this.request<FilePlan>(`/roots/${identifier(id)}/plans`, 'POST', { operations });
  };
  plans = async (id: string) => this.request<FilePlan[]>(`/roots/${identifier(id)}/plans`);
  privatePlan = async (id: string) => this.request<FilePlan & { root_path: string }>(`/plans/${identifier(id)}`);
  confirm = async (id: string, digest: string, requestId: string) => {
    if (typeof digest !== 'string' || !/^[a-f0-9]{64}$/.test(digest)) throw new Error('invalid_request');
    return this.request<FileJob>(`/plans/${identifier(id)}/confirm`, 'POST', { digest, request_id: identifier(requestId) });
  };
  fileJobs = async (id: string) => this.request<FileJob[]>(`/roots/${identifier(id)}/file-jobs`);
  stopFile = async (id: string) => { await this.request(`/file-jobs/${identifier(id)}/cancel`, 'POST', {}); };
  undo = async (id: string) => this.request<FilePlan>(`/file-jobs/${identifier(id)}/undo`, 'POST', {});
  document = async (id: string, path: string) => this.request<DocumentPreview>(`/roots/${identifier(id)}/document?path=${encodeURIComponent(bounded(path, 240))}`, 'GET', undefined, 50000);
  indexDocuments = async (id: string, paths: string[], semantic: boolean) => {
    if (!Array.isArray(paths) || !paths.length || paths.length > 20) throw new Error('invalid_request');
    return this.request<{ documents: number; chunks: number; mode: string; warnings: string[] }>(`/roots/${identifier(id)}/document-index`, 'POST', { paths: paths.map(p => bounded(p, 240)), semantic: boolean(semantic) }, 300000);
  };
  knowledge = async (id: string, query: string, semantic: boolean) => this.request<KnowledgeResults>(`/roots/${identifier(id)}/knowledge?query=${encodeURIComponent(bounded(query, 200))}&semantic=${boolean(semantic)}`, 'GET', undefined, 120000);
  transform = async (id: string, value: DocumentTransform) => {
    if (!value || !Array.isArray(value.paths) || !value.paths.length || value.paths.length > 10 || !['merge', 'split', 'rotate', 'images', 'docx_pdf'].includes(value.kind) || !Array.isArray(value.pages) || value.pages.length > 200 || value.pages.some(p => !Number.isInteger(p) || p < 1 || p > 200) || !Number.isInteger(value.rotation)) throw new Error('invalid_request');
    return this.request<FilePlan>(`/roots/${identifier(id)}/transform`, 'POST', { ...value, paths: value.paths.map(p => bounded(p, 240)), target: bounded(value.target, 240) }, 50000);
  };
  bindVault = async (id: string) => this.request<{ vault_root_id: string }>(`/roots/${identifier(id)}/vault`, 'POST', {});
  documentSettings = async () => this.request<{ vault_root_id: string | null }>('/document-settings');
  note = async (id: string, target: string, text: string) => this.request<FilePlan>(`/roots/${identifier(id)}/note`, 'POST', { target: bounded(target, 240), text: bounded(text, 100000) });
  indexedDocuments = async (id: string) => this.request<{ path: string; chunks: number; source_hash: string }[]>(`/roots/${identifier(id)}/document-index`);
  forgetDocument = async (id: string, path: string) => { await this.request(`/roots/${identifier(id)}/document-index?path=${encodeURIComponent(bounded(path, 240))}`, 'DELETE'); };
}
