import { expect, it } from 'vitest';
import { AudioCoordinator, type AudioPort } from '../../src/audio/coordinator';
import { pcmWav } from '../../src/audio/recorder';
import type { CompanionBridge } from '../../shared/contracts';

class AudioDevice implements AudioPort {
  src = ''; ended = false; onended: (() => void) | null = null;
  paused = true;
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
it('pause resumes the same segment and replay uses the last text, while stop invalidates resume', async () => {
  const device = new AudioDevice(); const spoken: string[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: async (text: string) => { spoken.push(text); return new Uint8Array([1]); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => device);
  const reading = audio.read('朗读这句');
  await new Promise(resolve => setTimeout(resolve, 0));
  audio.pause(); expect(audio.state).toBe('paused'); expect(device.paused).toBe(true);
  await audio.resume(); expect(audio.state).toBe('speaking'); expect(spoken).toHaveLength(1);
  await audio.stopVoice(); await reading; await audio.resume(); expect(audio.state).toBe('idle');
  const replay = audio.replay(); await new Promise(resolve => setTimeout(resolve, 0));
  expect(spoken).toEqual(['朗读这句', '朗读这句']); await audio.stopVoice(); await replay;
});
it('starting recording stops a playing speech segment and owns the audio state', async () => {
  const speech = new AudioDevice();
  const bridge = { cancelVoice: async () => {}, synthesize: async () => new Uint8Array([1]) } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => speech);
  const reading = audio.read('你好');
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(audio.state).toBe('speaking'); expect(speech.paused).toBe(false);
  expect(await audio.beginRecording()).toBe(true); await reading;
  expect(speech.paused).toBe(true); expect(audio.state).toBe('recording');
  audio.endRecording(); expect(audio.state).toBe('idle');
});

it('a cancelled TTS response cannot create playback after a newer operation', async () => {
  let finish!: (data: Uint8Array) => void;
  const devices: AudioDevice[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: () => new Promise<Uint8Array>(resolve => { finish = resolve; }) } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); devices.push(device); return device; });
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

it('reads the entire long reply in bounded chunks and returns to idle', async () => {
  const spoken: string[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: async (text: string) => { spoken.push(text); return new Uint8Array([1, 2]); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); device.ended = true; return device; });
  await audio.read('黑塔'.repeat(550));
  expect(spoken.map(text => text.length)).toEqual([500, 500, 100]);
  expect(spoken.join('')).toBe('黑塔'.repeat(550));
  expect(audio.state).toBe('idle');
});

it('audio subscriptions remain active when the companion service is restarted', async () => {
  const bridge = { cancelVoice: async () => {} } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => new AudioDevice());
  let updates = 0; const unsubscribe = audio.subscribe(() => { updates++; });
  audio.dispose(); updates = 0;
  await audio.beginRecording();
  expect(updates).toBeGreaterThan(0); unsubscribe();
});

it.each(['read', 'record'] as const)('a stop during initial IPC cancellation prevents late %s from starting', async action => {
  const cancellations: (() => void)[] = []; const spoken: string[] = [];
  const bridge = { cancelVoice: () => new Promise<void>(resolve => cancellations.push(resolve)), synthesize: async (text: string) => { spoken.push(text); return new Uint8Array([1]); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); device.ended = true; return device; });
  const old = action === 'read' ? audio.read('旧回答') : audio.beginRecording();
  const stopping = audio.stopVoice(); cancellations[1](); await stopping;
  cancellations[0]();
  await new Promise(resolve => setTimeout(resolve, 0));
  const state = audio.state; const calls = spoken.length;
  for (const resolve of cancellations) resolve();
  await old;
  expect(calls).toBe(0); expect(state).toBe('idle');
});

it('stopping a playing long reply pauses it and prevents the next chunk', async () => {
  const spoken: string[] = []; const devices: AudioDevice[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: async (text: string) => { spoken.push(text); return new Uint8Array([1]); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); devices.push(device); return device; });
  const reading = audio.read('黑塔'.repeat(300));
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(audio.state).toBe('speaking');
  await audio.stopVoice(); await reading;
  devices[0].onended?.(); await new Promise(resolve => setTimeout(resolve, 0));
  expect(devices[0].paused).toBe(true); expect(spoken).toHaveLength(1); expect(audio.state).toBe('idle');
});
