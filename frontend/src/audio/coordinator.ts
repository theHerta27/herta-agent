import type { CompanionBridge } from '../../shared/contracts';

export interface AudioPort {
  src: string; ended: boolean;
  onended: ((event: Event) => void) | null; play(): Promise<void>; pause(): void;
  addEventListener?(type: string, listener: () => void): void;
}

/** Owns local speech playback and cancellation; microphone capture stays in Recorder. */
export class AudioCoordinator {
  private generation = 0;
  private speech?: AudioPort;
  private url?: string;
  private finishSpeech?: () => void;
  private listeners = new Set<() => void>();
  state: 'idle' | 'loading' | 'speaking' | 'paused' | 'recording' = 'idle';
  private lastText = '';
  error = '';
  constructor(private bridge: CompanionBridge, private createAudio: () => AudioPort) {}
  subscribe = (handler: () => void) => { this.listeners.add(handler); return () => { this.listeners.delete(handler); }; };
  snapshot = () => this.state + ':' + this.error;
  private update(state: typeof this.state, error = '') { this.state = state; this.error = error; for (const handler of this.listeners) handler(); }
  async stopVoice() {
    ++this.generation;
    this.speech?.pause(); this.speech = undefined;
    this.finishSpeech?.(); this.finishSpeech = undefined;
    if (this.url) URL.revokeObjectURL(this.url); this.url = undefined;
    this.update('idle');
    await this.bridge.cancelVoice().catch(() => {});
  }
  async beginRecording() {
    const stopping = this.stopVoice(); const generation = this.generation;
    await stopping;
    if (generation !== this.generation) return false;
    this.update('recording'); return true;
  }
  endRecording() { this.update('idle'); }
  pause() { if (this.state === 'speaking' && this.speech) { this.speech.pause(); this.update('paused'); } }
  async resume() {
    if (this.state !== 'paused' || !this.speech) return;
    const generation = this.generation;
    try { await this.speech.play(); if (generation === this.generation) this.update('speaking'); }
    catch { if (generation === this.generation) { await this.stopVoice(); this.update('idle', '播放失败，请重播。'); } }
  }
  replay() { return this.lastText ? this.read(this.lastText) : Promise.resolve(); }
  async read(text: string) {
    this.lastText = text;
    const stopping = this.stopVoice(); const generation = this.generation;
    await stopping;
    if (generation !== this.generation) return;
    this.update('loading');
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
  dispose() { void this.stopVoice(); }
}
