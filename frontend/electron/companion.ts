import { BackendClient, identifier } from './backend-client';
import type { CompanionAction, CompanionSnapshot, MusicTrack, Playback, VoiceStatus } from '../shared/contracts';

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid_request');
  return value as Record<string, unknown>;
}
function text(value: unknown, max: number): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max || value.includes('\0')) throw new Error('invalid_request');
  return value;
}
function number(value: unknown, min: number, max: number): number {
  if (!Number.isInteger(value) || (value as number) < min || (value as number) > max) throw new Error('invalid_request');
  return value as number;
}

export function actionRequest(value: unknown): { path: string; method: string; body?: object } {
  const input = object(value);
  const keys: Record<string, string[]> = {
    music: ['kind', 'action', 'track_id', 'volume'], create_reminder: ['kind', 'title', 'due_at', 'repeat'],
    cancel_reminder: ['kind', 'id'], snooze: ['kind', 'id', 'minutes'],
    approve_memory: ['kind', 'id'], delete_memory: ['kind', 'id'], ack: ['kind', 'id'],
    memory: ['kind', 'text'], preferences: ['kind', 'value'],
  };
  if (typeof input.kind !== 'string' || !Object.hasOwn(keys, input.kind) || Object.keys(input).some(key => !keys[input.kind as string].includes(key))) throw new Error('invalid_request');
  switch (input.kind) {
    case 'music': {
      if (!['play', 'pause', 'next', 'previous', 'volume', 'stop'].includes(input.action as string)) throw new Error('invalid_request');
      const body: Record<string, unknown> = { action: input.action };
      if (input.track_id !== undefined) body.track_id = identifier(input.track_id);
      if (input.volume !== undefined) body.volume = number(input.volume, 0, 100);
      if (input.action === 'volume' && input.volume === undefined) throw new Error('invalid_request');
      return { path: '/companion/music/control', method: 'POST', body };
    }
    case 'create_reminder': {
      const due = text(input.due_at, 60);
      if (!/(Z|[+-]\d{2}:\d{2})$/.test(due) || !Number.isFinite(Date.parse(due)) || !['once', 'daily', 'weekly'].includes(input.repeat as string)) throw new Error('invalid_request');
      return { path: '/companion/reminders', method: 'POST', body: { title: text(input.title, 200), due_at: due, repeat: input.repeat } };
    }
    case 'cancel_reminder': return { path: `/companion/reminders/${identifier(input.id)}/cancel`, method: 'POST', body: {} };
    case 'snooze': return { path: `/companion/reminders/${identifier(input.id)}/snooze`, method: 'POST', body: { minutes: number(input.minutes, 1, 10080) } };
    case 'approve_memory': return { path: `/companion/memories/${identifier(input.id)}/approve`, method: 'POST', body: {} };
    case 'delete_memory': return { path: `/companion/memories/${identifier(input.id)}`, method: 'DELETE' };
    case 'ack': return { path: `/companion/deliveries/${identifier(input.id)}/ack`, method: 'POST', body: {} };
    case 'memory': return { path: '/companion/memories', method: 'POST', body: { text: text(input.text, 200) } };
    case 'preferences': {
      const prefs = object(input.value);
      if (Object.keys(prefs).some(key => !['nickname', 'volume', 'auto_read', 'allow_tools', 'quiet_start', 'quiet_end'].includes(key))) throw new Error('invalid_request');
      if (typeof prefs.nickname !== 'string' || prefs.nickname.length > 60 || typeof prefs.auto_read !== 'boolean' || typeof prefs.allow_tools !== 'boolean') throw new Error('invalid_request');
      number(prefs.volume, 0, 100); number(prefs.quiet_start, 0, 23); number(prefs.quiet_end, 0, 23);
      return { path: '/companion/preferences', method: 'PUT', body: prefs };
    }
    default: throw new Error('invalid_request');
  }
}

export class CompanionClient {
  private voiceAbort: AbortController | undefined;
  constructor(readonly client: BackendClient) {}
  snapshot = () => this.client.json<CompanionSnapshot>('/companion');
  action(value: CompanionAction): Promise<unknown> {
    const request = actionRequest(value);
    return this.client.json(request.path, request.method, request.body);
  }
  importTracks = (paths: string[]) => this.client.json<MusicTrack[]>('/companion/music/import', 'POST', { paths });
  report(revision: unknown, actual: unknown, error: unknown = ''): Promise<void> {
    number(revision, 0, Number.MAX_SAFE_INTEGER);
    if (!['playing', 'paused', 'stopped', 'error'].includes(actual as string) || typeof error !== 'string' || error.length > 200) throw new Error('invalid_request');
    return this.client.json('/companion/music/report', 'POST', { revision, actual, error });
  }
  voiceStatus = () => this.client.json<VoiceStatus>('/companion/speech');
  cancelVoice() { this.voiceAbort?.abort(); this.voiceAbort = undefined; }
  private async voice(path: string, body: BodyInit, contentType: string): Promise<Response> {
    this.cancelVoice();
    const controller = new AbortController(); this.voiceAbort = controller;
    const response = await fetch(this.client.endpoint() + path, {
      method: 'POST', body, headers: { 'Content-Type': contentType }, redirect: 'error',
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(120000)]),
    });
    if (!response.ok) throw new Error(`voice_http_${response.status}`);
    return response;
  }
  async synthesize(value: unknown): Promise<Uint8Array> {
    const response = await this.voice('/companion/speech/tts', JSON.stringify({ text: text(value, 1500) }), 'application/json');
    const audio = new Uint8Array(await response.arrayBuffer());
    if (audio.length > 12_000_000) throw new Error('voice_too_large');
    return audio;
  }
  async transcribe(value: unknown): Promise<{ text: string }> {
    if (!(value instanceof Uint8Array) || value.byteLength > 2_000_000 || value.byteLength < 44) throw new Error('invalid_audio');
    const response = await this.voice('/companion/speech/asr', new Uint8Array(value), 'audio/wav');
    return response.json();
  }
}

export function mediaUrl(id: string) { return `herta-media://music/${identifier(id)}`; }
export function playbackLabel(value: Playback) { return ({ playing: '正在播放', paused: '已暂停', stopped: '已停止', pending: '正在处理', error: '播放失败' })[value.actual]; }
