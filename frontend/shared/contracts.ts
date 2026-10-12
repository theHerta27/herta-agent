import type { WorkspaceBridge } from './workspace-contracts';
import type { ProductivityBridge } from './productivity-contracts';

export type BackendStatus = {
  state: 'starting' | 'ready' | 'needs_configuration' | 'unavailable' | 'stopping' | 'stopped';
  reason?: 'start_failed' | 'process_exited' | 'stop_failed';
  ragAvailable?: boolean; embeddingProvider?: string; embeddingModel?: string; mcpAvailable?: boolean; mcpError?: string;
};

export interface DesktopBridge {
  workspace: WorkspaceBridge;
  companion: CompanionBridge;
  productivity: ProductivityBridge;
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

export interface CompanionPreferences { nickname: string; auto_read: boolean; allow_tools: boolean; quiet_start: number; quiet_end: number }
export interface Reminder { id: string; title: string; due_at: string; repeat: 'once' | 'daily' | 'weekly'; enabled: boolean }
export interface Delivery { id: string; reminder_id: string; title: string; due_at: string; created_at: string; notified: number }
export interface CompanionMemory { id: string; text: string; status: 'pending' | 'approved' }
export interface CompanionSnapshot { preferences: CompanionPreferences; reminders: Reminder[]; deliveries: Delivery[]; memories: CompanionMemory[] }
export type CompanionAction =
  | { kind: 'create_reminder'; title: string; due_at: string; repeat: Reminder['repeat'] }
  | { kind: 'cancel_reminder' | 'approve_memory' | 'delete_memory' | 'ack'; id: string }
  | { kind: 'snooze'; id: string; minutes: number }
  | { kind: 'memory'; text: string }
  | { kind: 'preferences'; value: CompanionPreferences };
export interface VoiceStatus { tts: boolean; asr: boolean; detail: string }
export interface CompanionBridge {
  snapshot(): Promise<CompanionSnapshot>;
  action(action: CompanionAction): Promise<unknown>;
  voiceStatus(): Promise<VoiceStatus>;
  synthesize(text: string): Promise<Uint8Array>;
  transcribe(wav: Uint8Array): Promise<{ text: string }>;
  cancelVoice(): Promise<void>;
}
