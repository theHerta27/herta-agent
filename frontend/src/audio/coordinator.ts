import type { CompanionBridge, Playback } from '../../shared/contracts';

export interface AudioPort {
  src: string; volume: number; currentTime: number; ended: boolean;
  onended: ((event: Event) => void) | null; play(): Promise<void>; pause(): void;
  addEventListener?(type: string, listener: () => void): void;
}

export class AudioCoordinator {
  private generation = 0;
  private revision = -1;
  private selectedVolume = .4;
  private ducked = false;
  private speech?: AudioPort;
  private url?: string;
  private finishSpeech?: () => void;
  private listeners = new Set<() => void>();
  state: 'idle' | 'loading' | 'speaking' | 'recording' = 'idle';
  error = '';
  constructor(private bridge: CompanionBridge, readonly music: AudioPort, private createAudio: () => AudioPort) {}
  subscribe = (handler: () => void) => { this.listeners.add(handler); return () => { this.listeners.delete(handler); }; };
  snapshot = () => this.state + ':' + this.error;
  private update(state: typeof this.state, error = '') { this.state = state; this.error = error; for (const handler of this.listeners) handler(); }
  private volume() { this.music.volume = this.selectedVolume * (this.ducked ? .2 : 1); }
  async apply(value: Playback) {
    if (this.revision === value.revision) return;
    this.revision = value.revision; this.selectedVolume = value.volume / 100; this.volume();
    try {
      if (value.track_id) {
        const source = 'herta-media://music/' + value.track_id;
        if (this.music.src !== source) this.music.src = source;
      }
      if (value.desired === 'playing') {
        if (this.music.ended) this.music.currentTime = 0;
        await this.music.play();
      } else {
        this.music.pause(); if (value.desired === 'stopped') this.music.currentTime = 0;
      }
      if (this.revision === value.revision) await this.bridge.reportPlayback(value.revision, value.desired);
    } catch {
      if (this.revision === value.revision) await this.bridge.reportPlayback(value.revision, 'error', '音频不可用，请重新导入或选择其他格式。').catch(() => {});
    }
  }
  async stopVoice() {
    ++this.generation;
    this.speech?.pause(); this.speech = undefined;
    this.finishSpeech?.(); this.finishSpeech = undefined;
    if (this.url) URL.revokeObjectURL(this.url); this.url = undefined;
    this.ducked = false; this.volume(); this.update('idle');
    await this.bridge.cancelVoice().catch(() => {});
  }
  async beginRecording() {
    const stopping = this.stopVoice(); const generation = this.generation;
    await stopping;
    if (generation !== this.generation) return false;
    this.ducked = true; this.volume(); this.update('recording'); return true;
  }
  endRecording() { this.ducked = false; this.volume(); this.update('idle'); }
  async read(text: string) {
    const stopping = this.stopVoice(); const generation = this.generation;
    await stopping;
    if (generation !== this.generation) return;
    this.ducked = true; this.volume(); this.update('loading');
    try {
      const content = text.replace(/[#*_`]/g, '').trim();
      for (let offset = 0; offset < content.length; offset += 500) {
        this.update('loading');
        const bytes = await this.bridge.synthesize(content.slice(offset, offset + 500));
        if (generation !== this.generation) return;
        this.url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: 'audio/wav' }));
        const audio = this.createAudio(); this.speech = audio; audio.src = this.url;
        await audio.play();
        if (generation !== this.generation) return;
        this.update('speaking');
        if (!audio.ended) await new Promise<void>((resolve, reject) => {
          this.finishSpeech = resolve; audio.onended = () => resolve();
          audio.addEventListener?.('error', () => reject(new Error('audio_failed')));
        });
        if (generation !== this.generation) return;
        this.finishSpeech = undefined; this.speech = undefined;
        URL.revokeObjectURL(this.url); this.url = undefined;
      }
      if (generation === this.generation) await this.stopVoice();
    } catch {
      if (generation === this.generation) { await this.stopVoice(); this.update('idle', '本地朗读失败，请检查语音模型或点击重试。'); }
    }
  }
  dispose() { this.revision = -1; this.music.pause(); void this.stopVoice(); }
}
