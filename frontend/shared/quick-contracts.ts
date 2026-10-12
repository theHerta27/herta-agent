export interface QuickInput { kind: 'draft' | 'send'; sessionId: string | null; expectedDraft: string; text: string }
export interface QuickState { sessionId: string | null; draft: string; busy: boolean; ready: boolean; title: string; lastReply: string }
export interface QuickBridge {
  open(): Promise<void>;
  publish(state: QuickState): Promise<void>;
  onInput(handler: (request: { id: string; input: QuickInput }) => void): () => void;
  respond(id: string, error?: string): Promise<void>;
}
export interface QuickWindowBridge {
  state(): Promise<QuickState | null>;
  onState(handler: (state: QuickState) => void): () => void;
  input(value: QuickInput): Promise<void>;
  close(): Promise<void>;
  showMain(): Promise<void>;
}
