import { expect, it } from 'vitest';
import { AudioCoordinator, type AudioPort } from '../../src/audio/coordinator';
import { pcmWav } from '../../src/audio/recorder';
import type { CompanionBridge } from '../../shared/contracts';
import { speechChunks } from '../../src/audio/speech-chunks';

class AudioDevice implements AudioPort {
  src = ''; ended = false; onended: (() => void) | null = null;
  paused = true;
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
it('skips non-audible blank segments and still reads the final paragraph', async () => {
  const spoken: string[] = [];
  const bridge = { cancelVoice: async () => {}, synthesize: async (text: string) => { if (!text.trim()) throw new Error('blank speech'); spoken.push(text); return new Uint8Array([1]); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); device.ended = true; return device; });
  await audio.read('材料'.repeat(60) + '\n'.repeat(120) + '最后一段也必须朗读。');
  expect(spoken.at(-1)).toContain('最后一段也必须朗读。');
  expect(audio.error).toBe('');
});
it('bounds uninterrupted text, prefers sentence boundaries and preserves every character', () => {
  const text = '来了？今天想弄清什么。\n' + '长材料'.repeat(100);
  const chunks = speechChunks(text);
  expect(chunks.join('')).toBe(text);
  expect(chunks.every(chunk => chunk.length <= 120)).toBe(true);
  expect(chunks[0]).toContain('来了？今天想弄清什么。');
});

it('prepares the next segment during playback and discards it if stopped', async () => {
  const spoken: string[] = [], devices: AudioDevice[] = [];
  let release!: (data: Uint8Array) => void;
  const bridge = { cancelVoice: async () => {}, synthesize: (text: string) => { spoken.push(text); return spoken.length === 1 ? Promise.resolve(new Uint8Array([1])) : new Promise<Uint8Array>(resolve => { release = resolve; }); } } as unknown as CompanionBridge;
  const audio = new AudioCoordinator(bridge, () => { const device = new AudioDevice(); devices.push(device); return device; });
  const reading = audio.read('材料'.repeat(150));
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(spoken).toHaveLength(2);
  expect(devices).toHaveLength(1);
  await audio.stopVoice(); release(new Uint8Array([2])); await reading;
  expect(devices).toHaveLength(1);
  expect(devices[0].paused).toBe(true);
  expect(audio.state).toBe('idle');
});
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
  expect(spoken.every(text => text.length <= 120)).toBe(true);
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
  expect(devices[0].paused).toBe(true); expect(devices).toHaveLength(1); expect(spoken.length).toBeLessThanOrEqual(2); expect(audio.state).toBe('idle');
});
