export type BackendStatus = {
  state: 'starting' | 'ready' | 'needs_configuration' | 'unavailable' | 'stopping' | 'stopped';
  reason?: 'start_failed' | 'process_exited' | 'stop_failed';
  ragAvailable?: boolean; embeddingProvider?: string; embeddingModel?: string; mcpAvailable?: boolean; mcpError?: string;
};

export interface DesktopBridge {
  getSettings(): Promise<PublicSettings>;
  applySettings(settings: PublicSettings): Promise<SettingsApplyResult>;
  getRunDiagnostics(id: string): Promise<RunDiagnostics>;
  getBackendStatus(): Promise<BackendStatus>;
  onBackendStatus(handler: (status: BackendStatus) => void): () => void;
  listSessions(afterId?: string, limit?: number): Promise<SessionRecord[]>;
  createSession(): Promise<SessionRecord>;
  getSession(id: string, afterSeq?: number, limit?: number): Promise<SessionPage>;
  getRun(id: string): Promise<{ run: RunRecord; cancel_requested: boolean }>;
  startRun(request: RunRequest): Promise<void>;
  cancelRequest(clientRequestId: string): Promise<void>;
  onRunEvents(handler: (packet: RunPacket) => void): () => void;
}

export interface SessionRecord { session_id: string; created_at: string; updated_at: string }
export interface ToolCall { id: string; name: string; arguments: string }
export interface Message { role: 'user' | 'assistant' | 'tool' | 'system'; content: string | null; tool_calls: ToolCall[]; tool_call_id: string | null }
export interface MessageRecord { message_id: string; session_id: string; run_id: string; seq: number; step: number; message: Message }
export type RunStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
export interface RunRecord { run_id: string; session_id: string; status: RunStatus; error: string | null; config: { model: string }; steps: number }
export interface SessionPage { session: SessionRecord; messages: MessageRecord[]; current_run: RunRecord | null }
export interface ServiceEvent { schema_version: 1; type: string; session_id: string; run_id: string; seq: number; timestamp: string; payload: Record<string, unknown> }
export interface RunRequest { clientRequestId: string; sessionId: string; text: string }
export interface RunPacket { clientRequestId: string; events?: ServiceEvent[]; closed?: boolean; rejected?: number }

declare global { interface Window { herta: DesktopBridge } }

export interface PublicSettings {
  chatBaseUrl: string; chatModel: string; embeddingBaseUrl: string; embeddingModel: string;
  contextWindow: number; outputReserve: number; summaryEnabled: boolean;
  embeddingProvider: 'auto' | 'local' | 'remote';
}
export interface SummaryReference { summary_id: string; source_start: number; source_end: number; source_hash: string; algorithm: string }
export interface ContextDiagnostic {
  step: number; policy_version: string; persona_hash: string; estimated_input_tokens: number; input_budget: number;
  tool_schema_tokens: number; retained_message_indices: number[]; omitted_message_count: number;
  summary_refs: SummaryReference[]; evidence_refs: string[]; reason: string;
}
export interface RunDiagnostics { contexts: ContextDiagnostic[]; tools: Record<string, unknown>[] }
export interface SettingsApplyResult { settings: PublicSettings; backend: BackendStatus }
