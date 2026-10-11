import { afterEach, expect, it, vi } from 'vitest';
import { CompanionRuntime } from '../../src/state/companion-runtime';
import type { CompanionBridge, CompanionSnapshot } from '../../shared/contracts';

class AudioDevice {
  src = ''; volume = 1; currentTime = 0; ended = false; onended = null;
  plays = 0; paused = true;
  async play() { this.plays++; this.paused = false; }
  pause() { this.paused = true; }
}
const data = {
  preferences: { nickname: '', volume: 40, auto_read: false, allow_tools: true, quiet_start: 23, quiet_end: 8 }, tracks: [], reminders: [], memories: [], deliveries: [],
  playback: { revision: 3, desired: 'playing', actual: 'pending', track_id: 'track', volume: 40, error: '' },
} as CompanionSnapshot;
afterEach(() => vi.unstubAllGlobals());

it('ignores a late snapshot after stopping and resumes the same revision on restart', async () => {
  vi.stubGlobal('Audio', AudioDevice);
  let resolve!: (value: CompanionSnapshot) => void;
  const snapshot = vi.fn().mockImplementationOnce(() => new Promise<CompanionSnapshot>(done => { resolve = done; })).mockResolvedValue(data);
  const bridge = { snapshot, cancelVoice: async () => {}, reportPlayback: async () => {}, voiceStatus: async () => ({ tts: true, asr: true, detail: '' }) } as unknown as CompanionBridge;
  const runtime = new CompanionRuntime(bridge);
  try {
    runtime.start(); runtime.stop(); resolve(data);
    await new Promise(done => setTimeout(done, 0));
    const music = runtime.audio.music as unknown as AudioDevice;
    expect(music.plays).toBe(0);
    runtime.start(); await new Promise(done => setTimeout(done, 0));
    expect(music.plays).toBe(1);
    runtime.stop(); runtime.start(); await new Promise(done => setTimeout(done, 0));
    expect(music.plays).toBe(2);
  } finally { runtime.stop(); }
});
