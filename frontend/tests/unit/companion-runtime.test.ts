import { expect, it, vi } from 'vitest';
import { CompanionRuntime } from '../../src/state/companion-runtime';
import type { CompanionBridge, CompanionSnapshot } from '../../shared/contracts';

const data: CompanionSnapshot = {
  preferences: { nickname: '新称呼', auto_read: false, allow_tools: true, quiet_start: 23, quiet_end: 8 },
  reminders: [], memories: [], deliveries: [],
};

it('ignores a late snapshot after stopping and loads daily data after restart', async () => {
  let resolve!: (value: CompanionSnapshot) => void;
  const snapshot = vi.fn().mockImplementationOnce(() => new Promise<CompanionSnapshot>(done => { resolve = done; })).mockResolvedValue(data);
  const bridge = { snapshot, cancelVoice: async () => {}, voiceStatus: async () => ({ tts: true, asr: true, detail: '' }) } as unknown as CompanionBridge;
  const runtime = new CompanionRuntime(bridge);
  try {
    runtime.start(); runtime.stop(); resolve(data);
    await new Promise(done => setTimeout(done, 0));
    expect(runtime.state.data).toBeUndefined();
    runtime.start(); await new Promise(done => setTimeout(done, 0));
    expect(runtime.state.data?.preferences.nickname).toBe('新称呼');
    runtime.stop(); runtime.start(); await new Promise(done => setTimeout(done, 0));
    expect(runtime.state.voice).toEqual({ tts: true, asr: true, detail: '' });
  } finally { runtime.stop(); }
});
