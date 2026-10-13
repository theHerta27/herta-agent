export interface WorkspaceRoot { id: string; label: string; shared: boolean }
export interface FileEntry { name: string; path: string; kind: 'file' | 'directory'; size: number; hint: string }
export interface FileListing { entries: FileEntry[]; truncated: boolean; path?: string }
export interface TextPreview { path: string; text: string; start_line: number; truncated: boolean; source_hash?: string | null }
export interface SpaceReport {
  disk: { total: number; used: number; free: number }; logical_bytes: number; entries: number; skipped: number;
  partial: boolean; files: FileEntry[]; directories: { path: string; size: number; hint: string }[];
  duplicates: { size: number; count: number; paths: string[] }[]; duplicates_checked: boolean;
  hash_limited: boolean; limits: string; suggestions: string[];
}
export interface AnalysisJob { id: string; root_id: string; created_at: string; status: 'running' | 'completed' | 'cancelled' | 'interrupted' | 'failed'; report: SpaceReport | null; error: string | null }
export interface FileOperation { kind: 'copy' | 'move' | 'mkdir'; source?: string; target: string }
export interface FilePlan {
  id: string; root_id: string; root_label: string; created_at: string; digest: string;
  operations: { kind: string; source?: string; target: string; sha256?: string }[]; conflicts: string[]; undo_of?: string | null;
}
export interface FileJob {
  id: string; root_id: string; status: 'queued' | 'running' | 'completed' | 'cancelled' | 'failed' | 'interrupted' | 'undone';
  created_at: string; error: string | null; plan: FilePlan;
  receipts: { ordinal: number; state: 'intent' | 'done'; data: { operation: { kind: string; source?: string; target: string } } }[];
}
export interface DocumentPreview { path: string; source_hash: string; units: number; truncated: boolean; warnings: string[]; segments: { label: string; citation: string; text: string }[] }
export interface KnowledgeResults { results: { path: string; citation: string; text: string; score: number }[]; mode: string; warning: string | null; note: string }
export interface DocumentTransform { paths: string[]; kind: 'merge' | 'split' | 'rotate' | 'images' | 'docx_pdf'; target: string; pages: number[]; rotation: number }
export interface WorkspaceBridge {
  roots(): Promise<WorkspaceRoot[]>;
  chooseRoot(): Promise<WorkspaceRoot | null>;
  share(id: string, enabled: boolean): Promise<WorkspaceRoot>;
  revoke(id: string): Promise<void>;
  list(id: string, path?: string): Promise<FileListing>;
  search(id: string, query: string): Promise<FileListing>;
  read(id: string, path: string, shared?: boolean): Promise<TextPreview>;
  jobs(id: string): Promise<AnalysisJob[]>;
  start(id: string, duplicates: boolean): Promise<AnalysisJob>;
  cancel(id: string): Promise<void>;
  propose(id: string, operations: FileOperation[]): Promise<FilePlan>;
  plans(id: string): Promise<FilePlan[]>;
  plan(id: string): Promise<{ plan: FilePlan; job: FileJob | null }>;
  confirm(id: string, digest: string): Promise<FileJob | null>;
  fileJobs(id: string): Promise<FileJob[]>;
  stopFile(id: string): Promise<void>;
  undo(id: string): Promise<FilePlan>;
  document(id: string, path: string): Promise<DocumentPreview>;
  indexDocuments(id: string, paths: string[], semantic: boolean): Promise<{ documents: number; chunks: number; mode: string; warnings: string[] }>;
  knowledge(id: string, query: string, semantic: boolean): Promise<KnowledgeResults>;
  transform(id: string, request: DocumentTransform): Promise<FilePlan>;
  bindVault(id: string): Promise<{ vault_root_id: string }>;
  documentSettings(): Promise<{ vault_root_id: string | null }>;
  note(id: string, target: string, text: string): Promise<FilePlan>;
  indexedDocuments(id: string): Promise<{ path: string; chunks: number; source_hash: string }[]>;
  forgetDocument(id: string, path: string): Promise<void>;
}
