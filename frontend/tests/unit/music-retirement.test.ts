import { afterEach, expect, it, vi } from 'vitest';
import { actionRequest } from '../../electron/companion';
import { CompanionRuntime } from '../../src/state/companion-runtime';
import type { CompanionBridge, CompanionSnapshot } from '../../shared/contracts';

const preferences = { nickname: '开拓者', auto_read: false, allow_tools: true, quiet_start: 23, quiet_end: 8 };
// A late old payload must remain inert even if it requests playback.
const old = { preferences: { ...preferences, volume: 25 }, reminders: [], memories: [], deliveries: [], tracks: [{ id: 'old', title: '旧条目' }], playback: { revision: 7, desired: 'playing', actual: 'playing', track_id: 'old', volume: 25, error: '' } } as unknown as CompanionSnapshot;
afterEach(() => vi.unstubAllGlobals());

it('rejects retired commands and accepts current preferences without a volume field', () => {
  expect(() => actionRequest({ kind: 'music', action: 'pause' })).toThrow();
  expect(actionRequest({ kind: 'preferences', value: preferences })).toEqual({ path: '/companion/preferences', method: 'PUT', body: preferences });
  expect(() => actionRequest({ kind: 'preferences', value: { ...preferences, volume: 25 } })).toThrow();
});

it('refresh and restart do not allocate or play audio from old saved state', async () => {
  let allocated = 0;
  class UnexpectedAudio { constructor() { allocated++; } pause() {} async play() {} }
  vi.stubGlobal('Audio', UnexpectedAudio);
  const bridge = { snapshot: async () => old, voiceStatus: async () => ({ tts: true, asr: true, detail: '' }), cancelVoice: async () => {} } as unknown as CompanionBridge;
  const runtime = new CompanionRuntime(bridge);
  try {
    runtime.start(); await new Promise(resolve => setTimeout(resolve, 0));
    runtime.stop(); runtime.start(); await new Promise(resolve => setTimeout(resolve, 0));
    expect(allocated).toBe(0);
  } finally { runtime.stop(); }
});

it('focus creates a 45 minute reminder and performs no other daily action', async () => {
  vi.stubGlobal('Audio', class { pause() {} });
  const actions: unknown[] = [];
  const bridge = { action: async (value: unknown) => { actions.push(value); }, cancelVoice: async () => {} } as unknown as CompanionBridge;
  const runtime = new CompanionRuntime(bridge); runtime.state = { ...runtime.state, data: old };
  const before = Date.now(); await runtime.focus(); const after = Date.now();
  expect(actions).toHaveLength(1);
  const reminder = actions[0] as { kind: string; due_at: string; repeat: string };
  expect(reminder.kind).toBe('create_reminder'); expect(reminder.repeat).toBe('once');
  expect(Date.parse(reminder.due_at)).toBeGreaterThanOrEqual(before + 45 * 60000);
  expect(Date.parse(reminder.due_at)).toBeLessThanOrEqual(after + 45 * 60000);
});
