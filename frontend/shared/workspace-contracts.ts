export interface WorkspaceRoot { id: string; label: string; shared: boolean }
export interface FileEntry { name: string; path: string; kind: 'file' | 'directory'; size: number; hint: string }
export interface FileListing { entries: FileEntry[]; truncated: boolean; path?: string }
export interface TextPreview { path: string; text: string; start_line: number; truncated: boolean }
export interface SpaceReport {
  disk: { total: number; used: number; free: number }; logical_bytes: number; entries: number; skipped: number;
  partial: boolean; files: FileEntry[]; directories: { path: string; size: number; hint: string }[];
  duplicates: { size: number; count: number; paths: string[] }[]; duplicates_checked: boolean;
  hash_limited: boolean; limits: string; suggestions: string[];
}
export interface AnalysisJob { id: string; root_id: string; created_at: string; status: 'running' | 'completed' | 'cancelled' | 'interrupted' | 'failed'; report: SpaceReport | null; error: string | null }
export interface WorkspaceBridge {
  roots(): Promise<WorkspaceRoot[]>;
  chooseRoot(): Promise<WorkspaceRoot | null>;
  share(id: string, enabled: boolean): Promise<WorkspaceRoot>;
  revoke(id: string): Promise<void>;
  list(id: string, path?: string): Promise<FileListing>;
  search(id: string, query: string): Promise<FileListing>;
  read(id: string, path: string): Promise<TextPreview>;
  jobs(id: string): Promise<AnalysisJob[]>;
  start(id: string, duplicates: boolean): Promise<AnalysisJob>;
  cancel(id: string): Promise<void>;
}
