import { expect, it } from 'vitest';
import { AudioCoordinator, type AudioPort } from '../../src/audio/coordinator';
import { pcmWav } from '../../src/audio/recorder';
import type { CompanionBridge, Playback } from '../../shared/contracts';

class AudioDevice implements AudioPort {
  src = ''; volume = 1; currentTime = 0; ended = false; onended: (() => void) | null = null;
  paused = true;
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
const playback: Playback = { revision: 1, track_id: 'track', desired: 'playing', actual: 'pending', volume: 50, error: '' };

it('recording ducks music and stopping restores the selected volume', async () => {
  const music = new AudioDevice();
  const bridge = { cancelVoice: async () => {}, reportPlayback: async () => {} } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, music, () => new AudioDevice());
  await audio.apply(playback);
  expect(music.paused).toBe(false); expect(music.volume).toBe(.5);
  await audio.beginRecording(); expect(music.volume).toBe(.1);
  await audio.stopVoice(); expect(music.volume).toBe(.5);
});

it('a cancelled TTS response cannot create playback after a newer operation', async () => {
  let finish!: (data: Uint8Array) => void;
  const devices: AudioDevice[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: () => new Promise<Uint8Array>(resolve => { finish = resolve; }), reportPlayback: async () => {} } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, new AudioDevice(), () => { const device = new AudioDevice(); devices.push(device); return device; });
  const reading = audio.read('你好');
  await new Promise(resolve => setTimeout(resolve, 0));
  await audio.stopVoice(); finish(new Uint8Array([1, 2])); await reading;
  expect(devices).toHaveLength(0); expect(audio.state).toBe('idle');
});

it('resamples recorded PCM to a complete bounded 16k mono WAV', () => {
  const output = pcmWav([new Float32Array(48000).fill(.25)], 48000);
  const bytes = new DataView(output.buffer);
  expect(bytes.getUint32(24, true)).toBe(16000);
  expect(bytes.getUint32(40, true)).toBe(32000);
  expect(output.byteLength).toBe(32044);
  expect(bytes.getInt16(44, true)).toBe(8191);
  expect(() => pcmWav([new Float32Array(16000 * 61)], 16000)).toThrow();
});

it('reads the entire long reply in bounded chunks and restores music after completion', async () => {
  const spoken: string[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: async (text: string) => { spoken.push(text); return new Uint8Array([1, 2]); }, reportPlayback: async () => {} } as unknown as CompanionBridge;
  const music = new AudioDevice();
  const audio = new AudioCoordinator(bridge, music, () => { const device = new AudioDevice(); device.ended = true; return device; });
  await audio.apply(playback);
  await audio.read('黑塔'.repeat(550));
  expect(spoken.map(text => text.length)).toEqual([500, 500, 100]);
  expect(spoken.join('')).toBe('黑塔'.repeat(550));
  expect(audio.state).toBe('idle'); expect(music.volume).toBe(.5);
});

it('audio subscriptions remain active when the companion service is restarted', async () => {
  const bridge = { cancelVoice: async () => {} } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, new AudioDevice(), () => new AudioDevice());
  let updates = 0; const unsubscribe = audio.subscribe(() => { updates++; });
  audio.dispose(); updates = 0;
  await audio.beginRecording();
  expect(updates).toBeGreaterThan(0); unsubscribe();
});
