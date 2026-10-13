import type { BackendStatus, DesktopBridge, MessageRecord, RunDiagnostics, RunPacket, RunRecord, SessionRecord } from '../../shared/contracts';
import { mapFour, readHistory, readSessions } from './history-view';
import { newRun, reduceRun, type LiveRun } from './run-reducer';

export interface Conversation {
  messages: MessageRecord[]; runs: Record<string, RunRecord>; draft: string;
  diagnostics: Record<string, RunDiagnostics>; diagnosticsErrors: Record<string, string>;
  loading: boolean; loaded: boolean; error?: string; scrollTop?: number;
  request?: LiveRun;
}
export interface ChatState {
  backend: BackendStatus; selected: string | null; sessions: (SessionRecord & { title: string })[];
  views: Record<string, Conversation>; error?: string;
}
const empty = (): Conversation => ({ messages: [], runs: {}, diagnostics: {}, diagnosticsErrors: {}, draft: '', loading: false, loaded: false });

export class ChatStore {
  state: ChatState = { backend: { state: 'starting' }, selected: null, sessions: [], views: { draft: { ...empty(), loaded: true } } };
  private listeners = new Set<() => void>();
  private versions = new Map<string, number>();
  private selectionVersion = 0;
  private checking = new Set<string>();
  constructor(readonly bridge: DesktopBridge) {}
  subscribe = (handler: () => void) => { this.listeners.add(handler); return () => { this.listeners.delete(handler); }; };
  snapshot = () => this.state;
  protected emit() { this.state = { ...this.state }; for (const listener of this.listeners) listener(); }
  view(id = this.state.selected ?? 'draft') { return this.state.views[id] ??= empty(); }
  setDraft(text: string) { this.view().draft = text; this.emit(); }
  isBusy(view = this.view()) {
    return !!(view.request && view.request.phase !== 'done') || Object.values(view.runs).some(r => ['created', 'running'].includes(r.status));
  }
  async send(continuation?: { sessionId: string; text: string }): Promise<boolean> {
    let id = this.state.selected;
    if (continuation && continuation.sessionId !== id) return false;
    const view = this.view();
    const text = (continuation?.text ?? view.draft).trim();
    if (!text || text.length > MAX_CHAT_CHARS || view.loading || !view.loaded || this.isBusy(view) || this.state.backend.state !== 'ready') return false;
    const selection = this.selectionVersion;
    const request = newRun(crypto.randomUUID(), id ?? 'draft', text, view.messages.at(-1)?.seq ?? 0);
    request.preserveDraft = !!continuation;
    view.request = request; if (!continuation) view.draft = ''; view.error = undefined; this.emit();
    try {
      if (!id) {
        const session = await this.bridge.createSession();
        id = session.session_id; request.sessionId = id;
        this.state.views[id] = view;
        this.state.views.draft = { ...empty(), loaded: true };
        this.state.sessions.unshift({ ...session, title: text.slice(0, 60) });
        if (selection === this.selectionVersion) this.state.selected = id;
        this.emit();
      }
      if (request.phase === 'cancelling') { request.phase = 'done'; if (!request.preserveDraft) view.draft ||= text; this.emit(); return false; }
      await this.bridge.startRun({ clientRequestId: request.id, sessionId: id, text });
      return true;
    } catch {
      if (id) { view.error = '发送结果尚未确认，正在核对。'; void this.reconcile(id); }
      else { request.phase = 'done'; if (!request.preserveDraft) view.draft ||= text; view.error = '创建会话失败，请重试。'; }
      this.emit();
      return false;
    }
  }
  async stop() {
    const request = this.view().request;
    if (!request || ['done', 'cancelling'].includes(request.phase)) return;
    request.phase = 'cancelling'; this.emit();
    try { await this.bridge.cancelRequest(request.id); }
    catch { this.view(request.sessionId).error = '取消结果尚未确认，正在核对。'; void this.reconcile(request.sessionId); }
  }
  onPacket = (packet: RunPacket) => {
    const view = Object.values(this.state.views).find(v => v.request?.id === packet.clientRequestId);
    if (!view?.request || view.request.phase === 'done') return;
    if (packet.rejected) {
      view.request.phase = 'done'; view.request.partial = {};
      if (!view.request.preserveDraft) view.draft ||= view.request.text;
      view.error = ({ 409: '此会话正在运行，请等待当前轮结束。', 429: '同时运行数量已满，请稍后重试。', 503: '聊天或存储暂不可用，请检查启动配置。', 422: '消息格式不符合要求。' } as Record<number, string>)[packet.rejected] ?? '本轮请求被拒绝，请重试。';
      this.emit(); return;
    }
    for (const event of packet.events ?? []) view.request = reduceRun(view.request, event);
    if (packet.closed || view.request.phase === 'reconciling') void this.reconcile(view.request.sessionId);
    this.emit();
  };
  async reconcile(id: string) {
    const view = this.view(id);
    const requestId = view.request?.id;
    if (!requestId || this.checking.has(requestId)) return;
    this.checking.add(requestId);
    view.request!.phase = 'reconciling'; this.emit();
    try {
      for (let attempt = 0; attempt < 10; attempt++) {
        if (view.request?.id !== requestId) return;
        const loaded = await this.load(id);
        const request = view.request;
        const runId = request.runId ?? view.messages.find(m => m.seq > request.baseline && m.message.role === 'user')?.run_id;
        if (runId) request.runId = runId;
        const run = runId ? view.runs[runId] : undefined;
        if (loaded && run && !['created', 'running'].includes(run.status)) {
          request.phase = 'done'; request.partial = {};
          view.error = undefined;
          void this.refresh(); this.emit(); return;
        }
        if (attempt < 9) await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (view.request?.id === requestId) {
        view.request.phase = 'unknown'; view.request.partial = {};
        view.error = view.request.error ?? '本轮状态尚未确认。请核对状态，不要重复发送。'; this.emit();
      }
    } finally { this.checking.delete(requestId); }
  }
  saveScroll(id: string, top: number) { this.view(id).scrollTop = top; }
  select(id: string | null) {
    this.selectionVersion++;
    this.state.selected = id;
    this.emit();
    if (id) void this.load(id);
  }
  async connect(status: BackendStatus) {
    const first = !['ready', 'needs_configuration'].includes(this.state.backend.state);
    this.state.backend = status; this.emit();
    if (first && ['ready', 'needs_configuration'].includes(status.state)) await this.refresh();
  }
  async refresh() {
    try {
      const sessions = await readSessions(this.bridge.listSessions);
      const titles = new Map(this.state.sessions.map(s => [s.session_id, s.title]));
      this.state.sessions = sessions.map(s => ({ ...s, title: titles.get(s.session_id) ?? '对话 · ' + s.created_at.slice(0, 10) }));
      this.state.error = undefined; this.emit();
      await mapFour(this.state.sessions, async session => {
        if (titles.has(session.session_id)) return;
        try {
          const page = await this.bridge.getSession(session.session_id, 0, 1);
          const title = page.messages[0]?.message.content;
          if (title) { session.title = title.slice(0, 60); this.emit(); }
        } catch { /* Metadata remains usable when a preview read fails. */ }
      });
    } catch { this.state.error = '会话列表读取失败，请重试。'; this.emit(); }
  }
  async load(id: string): Promise<boolean> {
    const view = this.view(id);
    const version = (this.versions.get(id) ?? 0) + 1;
    this.versions.set(id, version);
    view.loading = true; view.error = undefined; this.emit();
    try {
      const history = await readHistory(this.bridge.getSession, id);
      const runs: Record<string, RunRecord> = {};
      const diagnostics = { ...view.diagnostics };
      const diagnosticsErrors = { ...view.diagnosticsErrors };
      await mapFour([...new Set(history.messages.map(m => m.run_id))], async runId => {
        const cached = view.runs[runId];
        runs[runId] = cached && !['created', 'running'].includes(cached.status) ? cached : (await this.bridge.getRun(runId)).run;
        if (!diagnostics[runId] || diagnosticsErrors[runId] || !cached || ['created', 'running'].includes(cached.status)) {
          try {
            diagnostics[runId] = await this.bridge.getRunDiagnostics(runId);
            delete diagnosticsErrors[runId];
          } catch { diagnosticsErrors[runId] = '诊断读取失败；已保存的对话仍可阅读。'; }
        }
      });
      if (history.currentRun) runs[history.currentRun.run_id] = history.currentRun;
      if (this.versions.get(id) !== version) return false;
      view.messages = history.messages; view.runs = runs; view.diagnostics = diagnostics; view.diagnosticsErrors = diagnosticsErrors; view.loaded = true;
      if (history.currentRun && ['created', 'running'].includes(history.currentRun.status) && (!view.request || view.request.phase === 'done')) {
        view.request = { ...newRun(crypto.randomUUID(), id, '', 0), runId: history.currentRun.run_id, phase: 'reconciling' };
        void this.reconcile(id);
      }
      return true;
    } catch { if (this.versions.get(id) === version) view.error = '会话读取失败，原有内容已保留。'; return false; }
    finally { if (this.versions.get(id) === version) { view.loading = false; this.emit(); } }
  }
}
import { MAX_CHAT_CHARS } from './referenceDraft';
