import { expect, it } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { DesktopSettings, defaultSettings, settingsEnvironment, validateSettings } from '../../electron/desktop-settings';

it('persists only public settings and maps environment without exporting keys', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  const env = { HERTA_API_KEY: 'secret', HERTA_EMBEDDING_API_KEY: 'embedding-secret' };
  const calls: string[] = [];
  let configured: NodeJS.ProcessEnv = {};
  const backend = { status: { state: 'ready' as const }, stop: async () => { calls.push('stop'); }, configureEnvironment: (value: NodeJS.ProcessEnv) => { configured = value; }, start: async () => { calls.push('start'); } };
  try {
    const settings = new DesktopSettings(join(dir, 'settings.json'), env, backend, () => 0, async () => 0);
    const next = { ...settings.get(), chatBaseUrl: 'https://provider.example/v1', chatModel: 'chat', embeddingBaseUrl: 'https://emb.example/v1', embeddingModel: 'embed', contextWindow: 8192, outputReserve: 1024, summaryEnabled: false };
    await settings.apply(next);
    expect(calls).toEqual(['stop', 'start']);
    expect(JSON.parse(readFileSync(join(dir, 'settings.json'), 'utf8'))).toEqual(next);
    expect(readFileSync(join(dir, 'settings.json'), 'utf8')).not.toContain('secret');
    expect(configured).toMatchObject({ HERTA_API_KEY: 'secret', HERTA_CONTEXT_WINDOW: '8192', HERTA_CONTEXT_OUTPUT_RESERVE: '1024', HERTA_CONTEXT_SUMMARY: 'false', HERTA_MODEL: 'chat', HERTA_EMBEDDING_MODEL: 'embed' });
    expect(new DesktopSettings(join(dir, 'settings.json'), env, backend, () => 0, async () => 0).get()).toEqual(next);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('blocks active and pending runs before stopping or writing, and blocks concurrent apply', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  let pending = 1;
  let active = 0;
  let release!: (count: number) => void;
  let waiting = false;
  let stops = 0;
  const backend = { status: { state: 'ready' as const }, stop: async () => { stops++; }, configureEnvironment: () => {}, start: async () => {} };
  try {
    const settings = new DesktopSettings(join(dir, 'settings.json'), {}, backend, () => pending, () => waiting ? new Promise<number>(resolve => { release = resolve; }) : Promise.resolve(active));
    await expect(settings.apply(settings.get())).rejects.toThrow('runs_active');
    pending = 0; active = 1;
    await expect(settings.apply(settings.get())).rejects.toThrow('runs_active');
    expect(stops).toBe(0);
    waiting = true;
    const applying = settings.apply(settings.get());
    expect(settings.applying).toBe(true);
    await expect(settings.apply(settings.get())).rejects.toThrow('settings_busy');
    release(0); await applying;
    expect(settings.applying).toBe(false);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('rejects credentials, unknown fields and invalid budgets; corrupt configuration falls back safely', () => {
  const base = defaultSettings({ HERTA_MODEL: 'configured', HERTA_API_KEY: 'secret' });
  expect(base.chatModel).toBe('configured');
  expect(settingsEnvironment(base, { HERTA_API_KEY: 'secret' }).HERTA_API_KEY).toBe('secret');
  for (const value of [{ ...base, apiKey: 'secret' }, { ...base, chatBaseUrl: 'https://user:password@example.com' }, { ...base, chatBaseUrl: 'https://example.com?api_key=secret' }, { ...base, outputReserve: base.contextWindow }, { ...base, contextWindow: 0 }, { ...base, summaryEnabled: 'false' }]) expect(() => validateSettings(value)).toThrow('invalid_settings');
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  try {
    writeFileSync(join(dir, 'settings.json'), '{broken');
    const backend = { status: { state: 'ready' as const }, stop: async () => {}, configureEnvironment: () => {}, start: async () => {} };
    expect(new DesktopSettings(join(dir, 'settings.json'), { HERTA_MODEL: 'configured' }, backend, () => 0, async () => 0).get()).toEqual(base);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('maps explicit local or remote embedding mode while auto clears an inherited override', () => {
  const base = defaultSettings({});
  expect(settingsEnvironment({ ...base, embeddingProvider: 'auto' }, { HERTA_EMBEDDING_PROVIDER: 'remote', HERTA_API_KEY: 'secret' })).not.toHaveProperty('HERTA_EMBEDDING_PROVIDER');
  expect(settingsEnvironment({ ...base, embeddingProvider: 'local' }, {}).HERTA_EMBEDDING_PROVIDER).toBe('local');
  expect(settingsEnvironment({ ...base, embeddingProvider: 'remote', embeddingBaseUrl: 'https://emb.example/v1', embeddingModel: 'embed' }, {}).HERTA_EMBEDDING_PROVIDER).toBe('remote');
  expect(() => validateSettings({ ...base, embeddingProvider: 'remote' })).toThrow('invalid_settings');
});

it('rejects context windows above the backend two million token boundary before any restart', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  let stops = 0;
  const backend = { status: { state: 'ready' as const }, stop: async () => { stops++; }, start: async () => {}, configureEnvironment: () => {} };
  try {
    const settings = new DesktopSettings(join(dir, 'settings.json'), {}, backend, () => 0, async () => 0);
    expect(validateSettings({ ...settings.get(), contextWindow: 2000000 }).contextWindow).toBe(2000000);
    await expect(settings.apply({ ...settings.get(), contextWindow: 2000001 })).rejects.toThrow('invalid_settings');
    expect(stops).toBe(0);
    expect(settings.get().contextWindow).toBe(32768);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('restores the previous configuration when start resolves but backend reports unavailable', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  const previous = defaultSettings({ HERTA_MODEL: 'working-model' });
  const calls: string[] = [];
  let attempts = 0;
  const backend = {
    status: { state: 'ready' } as import('../../shared/contracts').BackendStatus,
    stop: async () => { calls.push('stop'); backend.status = { state: 'stopped' }; },
    configureEnvironment: (env: NodeJS.ProcessEnv) => { calls.push('configure:' + env.HERTA_MODEL); },
    start: async () => { calls.push('start'); backend.status = ++attempts === 1 ? { state: 'unavailable', reason: 'start_failed' } : { state: 'ready' }; },
  };
  try {
    writeFileSync(join(dir, 'settings.json'), JSON.stringify(previous));
    const settings = new DesktopSettings(join(dir, 'settings.json'), {}, backend, () => 0, async () => 0);
    await expect(settings.apply({ ...previous, chatModel: 'broken-model' })).rejects.toThrow('settings_restart_failed');
    expect(settings.get()).toEqual(previous);
    expect(JSON.parse(readFileSync(join(dir, 'settings.json'), 'utf8'))).toEqual(previous);
    expect(backend.status.state).toBe('ready');
    expect(calls).toEqual(['stop', 'configure:broken-model', 'start', 'stop', 'configure:working-model', 'start']);
    expect(settings.applying).toBe(false);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

it('returns needs_configuration as an explicit result rather than reporting a ready service', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'herta-settings-'));
  const backend = { status: { state: 'needs_configuration' as const }, stop: async () => {}, start: async () => {}, configureEnvironment: () => {} };
  try {
    const settings = new DesktopSettings(join(dir, 'settings.json'), {}, backend, () => 0, async () => 0);
    const result = await settings.apply({ ...settings.get(), chatModel: '' });
    expect(result.backend.state).toBe('needs_configuration');
    expect(result.settings.chatModel).toBe('');
    expect(settings.get().chatModel).toBe('');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
