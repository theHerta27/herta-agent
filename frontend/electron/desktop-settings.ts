import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import type { BackendStatus, PublicSettings, SettingsApplyResult } from '../shared/contracts';

const fields = ['chatBaseUrl', 'chatModel', 'embeddingBaseUrl', 'embeddingModel', 'contextWindow', 'outputReserve', 'summaryEnabled', 'embeddingProvider'];

/** Only explicit public fields cross the renderer boundary. Credentials remain in process env. */
export function validateSettings(value: unknown): PublicSettings {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid_settings');
  const data = value as Record<string, unknown>;
  if (Object.keys(data).length !== fields.length || Object.keys(data).some(key => !fields.includes(key))) throw new Error('invalid_settings');
  for (const key of fields.slice(0, 4)) {
    if (typeof data[key] !== 'string' || (data[key] as string).length > 512 || /[\r\n\0]/.test(data[key] as string)) throw new Error('invalid_settings');
  }
  for (const key of ['chatBaseUrl', 'embeddingBaseUrl']) {
    const text = (data[key] as string).trim();
    if (!text) continue;
    try {
      const url = new URL(text);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error();
    } catch { throw new Error('invalid_settings'); }
  }
  if (!Number.isInteger(data.contextWindow) || (data.contextWindow as number) < 512 || (data.contextWindow as number) > 2000000
    || !Number.isInteger(data.outputReserve) || (data.outputReserve as number) < 64 || (data.outputReserve as number) >= (data.contextWindow as number) - 256
    || typeof data.summaryEnabled !== 'boolean') throw new Error('invalid_settings');
  if (!['auto', 'local', 'remote'].includes(data.embeddingProvider as string) || (data.embeddingProvider === 'remote' && (!(data.embeddingBaseUrl as string).trim() || !(data.embeddingModel as string).trim()))) throw new Error('invalid_settings');
  return {
    embeddingProvider: data.embeddingProvider as PublicSettings['embeddingProvider'],
    chatBaseUrl: (data.chatBaseUrl as string).trim(), chatModel: (data.chatModel as string).trim(),
    embeddingBaseUrl: (data.embeddingBaseUrl as string).trim(), embeddingModel: (data.embeddingModel as string).trim(),
    contextWindow: data.contextWindow as number, outputReserve: data.outputReserve as number, summaryEnabled: data.summaryEnabled,
  };
}

export function defaultSettings(env: NodeJS.ProcessEnv): PublicSettings {
  const fallback: PublicSettings = { chatBaseUrl: 'https://api.deepseek.com', chatModel: 'deepseek-flash', embeddingBaseUrl: '', embeddingModel: '', contextWindow: 32768, outputReserve: 2048, summaryEnabled: true, embeddingProvider: 'auto' };
  // Invalid public environment values must never cause raw credential-bearing URLs to reach IPC.
  const candidate = { ...fallback, embeddingProvider: env.HERTA_EMBEDDING_PROVIDER ?? 'auto', chatBaseUrl: env.HERTA_BASE_URL ?? fallback.chatBaseUrl, chatModel: env.HERTA_MODEL ?? fallback.chatModel, embeddingBaseUrl: env.HERTA_EMBEDDING_BASE_URL ?? '', embeddingModel: env.HERTA_EMBEDDING_MODEL ?? '', contextWindow: Number(env.HERTA_CONTEXT_WINDOW ?? fallback.contextWindow), outputReserve: Number(env.HERTA_CONTEXT_OUTPUT_RESERVE ?? fallback.outputReserve), summaryEnabled: !['false', '0', 'no', 'off'].includes((env.HERTA_CONTEXT_SUMMARY ?? 'true').toLowerCase()) };
  try { return validateSettings(candidate); } catch { return fallback; }
}

export function settingsEnvironment(settings: PublicSettings, env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = { ...env, HERTA_BASE_URL: settings.chatBaseUrl, HERTA_MODEL: settings.chatModel, HERTA_EMBEDDING_BASE_URL: settings.embeddingBaseUrl, HERTA_EMBEDDING_MODEL: settings.embeddingModel, HERTA_CONTEXT_WINDOW: String(settings.contextWindow), HERTA_CONTEXT_OUTPUT_RESERVE: String(settings.outputReserve), HERTA_CONTEXT_SUMMARY: String(settings.summaryEnabled) };
  if (settings.embeddingProvider === 'auto') delete result.HERTA_EMBEDDING_PROVIDER;
  else result.HERTA_EMBEDDING_PROVIDER = settings.embeddingProvider;
  return result;
}

interface OwnedBackend { readonly status: BackendStatus; stop(): Promise<void>; start(): Promise<void>; configureEnvironment(env: NodeJS.ProcessEnv): void }

export class DesktopSettings {
  private current: PublicSettings;
  applying = false;
  constructor(private file: string, private env: NodeJS.ProcessEnv, private backend: OwnedBackend, private pendingRuns: () => number, private activeRuns: () => Promise<number>) {
    this.current = defaultSettings(env);
    try {
      const saved = JSON.parse(readFileSync(file, 'utf8'));
      this.current = validateSettings({ embeddingProvider: 'auto', ...saved });
    } catch { /* Absent or invalid public config falls back to safe process defaults. */ }
  }
  get(): PublicSettings { return { ...this.current }; }
  environment(): NodeJS.ProcessEnv { return settingsEnvironment(this.current, this.env); }
  async apply(value: unknown): Promise<SettingsApplyResult> {
    if (this.applying) throw new Error('settings_busy');
    const next = validateSettings(value);
    const previous = this.get();
    // Lock synchronously before the health await; IPC run submission consults this lock.
    this.applying = true;
    try {
      if (this.pendingRuns() || await this.activeRuns()) throw new Error('runs_active');
      await this.backend.stop();
      let phase: 'restart' | 'write' = 'restart';
      try {
        this.backend.configureEnvironment(settingsEnvironment(next, this.env));
        await this.backend.start();
        // start() reports failures through status, including when its promise resolves.
        if (!['ready', 'needs_configuration'].includes(this.backend.status.state)) throw new Error('settings_restart_failed');
        const status = { ...this.backend.status };
        phase = 'write';
        mkdirSync(dirname(this.file), { recursive: true });
        const temporary = this.file + '.tmp';
        writeFileSync(temporary, JSON.stringify(next, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 });
        renameSync(temporary, this.file);
        this.current = next;
        return { settings: this.get(), backend: status };
      } catch {
        // Failed candidates never replace public settings. Restore the owned service too.
        try {
          await this.backend.stop();
          this.backend.configureEnvironment(settingsEnvironment(previous, this.env));
          await this.backend.start();
          if (!['ready', 'needs_configuration'].includes(this.backend.status.state)) throw new Error('recovery_failed');
        } catch { throw new Error('settings_recovery_failed'); }
        throw new Error(phase === 'restart' ? 'settings_restart_failed' : 'settings_write_failed');
      }
    } finally { this.applying = false; }
  }
}