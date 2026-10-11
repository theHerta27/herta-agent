import type { CompanionAction, CompanionBridge, CompanionSnapshot, VoiceStatus } from '../../shared/contracts';
import { AudioCoordinator } from '../audio/coordinator';

export interface DailyState { data?: CompanionSnapshot; voice: VoiceStatus; error: string }
export class CompanionRuntime {
  state: DailyState = { voice: { tts: false, asr: false, detail: '正在检查本地语音…' }, error: '' };
  private listeners = new Set<() => void>();
  private timer?: ReturnType<typeof setInterval>;
  private loading = false;
  private lastVoice = 0;
  private generation = 0;
  private active = false;
  readonly audio: AudioCoordinator;
  constructor(readonly bridge: CompanionBridge) {
    const music = new Audio();
    this.audio = new AudioCoordinator(bridge, music, () => new Audio());
    music.onended = () => { if (this.active) void this.action({ kind: 'music', action: 'next' }); };
  }
  subscribe = (handler: () => void) => { this.listeners.add(handler); return () => { this.listeners.delete(handler); }; };
  snapshot = () => this.state;
  private update(value: Partial<DailyState>) { this.state = { ...this.state, ...value }; for (const listener of this.listeners) listener(); }
  async refresh() {
    if (!this.active || this.loading) return; this.loading = true;
    const generation = this.generation;
    try {
      const data = await this.bridge.snapshot();
      if (generation !== this.generation || !this.active) return;
      this.update({ data, error: '' });
      void this.audio.apply(data.playback);
      if (Date.now() - this.lastVoice > 10000) {
        this.lastVoice = Date.now();
        const voice = await this.bridge.voiceStatus();
        if (generation === this.generation && this.active) this.update({ voice });
      }
    } catch { if (generation === this.generation && this.active) this.update({ error: '日常服务暂不可用，请等待服务就绪或重试。' }); }
    finally { this.loading = false; }
  }
  start() { if (this.active) return; this.active = true; this.lastVoice = 0; void this.refresh(); this.timer = setInterval(() => void this.refresh(), 700); }
  stop() { this.active = false; ++this.generation; if (this.timer) clearInterval(this.timer); this.timer = undefined; this.audio.dispose(); }
  async action(action: CompanionAction): Promise<boolean> {
    try { await this.bridge.action(action); await this.refresh(); return true; }
    catch { this.update({ error: '操作未完成，请检查时间、音乐文件或记录后重试。' }); return false; }
  }
  async importMusic() {
    try { await this.bridge.importMusic(); await this.refresh(); }
    catch { this.update({ error: '导入失败。每次选择不超过200首本地音频文件。' }); }
  }
  async focus() {
    const created = await this.action({ kind: 'create_reminder', title: '专注结束，起来休息一下。', due_at: new Date(Date.now() + 45 * 60000).toISOString(), repeat: 'once' });
    if (created && this.state.data?.tracks.length) await this.action({ kind: 'music', action: 'play' });
  }
}
