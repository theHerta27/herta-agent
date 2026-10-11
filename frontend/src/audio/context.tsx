import { createContext, useContext, useSyncExternalStore } from 'react';
import type { CompanionRuntime } from '../state/companion-runtime';

export const DailyContext = createContext<CompanionRuntime | null>(null);

export function ReadButton({ text }: { text: string }) {
  const runtime = useContext(DailyContext);
  if (!runtime) return null;
  return <ReadControl runtime={runtime} text={text} />;
}

export function AudioControls() {
  const runtime = useContext(DailyContext);
  if (!runtime) return null;
  return <AudioStatus runtime={runtime} />;
}

function AudioStatus({ runtime }: { runtime: CompanionRuntime }) {
  useSyncExternalStore(runtime.audio.subscribe, runtime.audio.snapshot);
  return <div className="audio-controls"><button disabled={runtime.audio.state === 'recording'} onClick={() => void runtime.audio.stopVoice()}>停止声音</button>
    {runtime.audio.error && <small role="alert">{runtime.audio.error}</small>}</div>;
}

function ReadControl({ runtime, text }: { runtime: CompanionRuntime; text: string }) {
  const { voice } = useSyncExternalStore(runtime.subscribe, runtime.snapshot);
  useSyncExternalStore(runtime.audio.subscribe, runtime.audio.snapshot);
  const active = runtime.audio.state !== 'idle';
  return <button className="read-button" disabled={!voice.tts || !text.trim() || runtime.audio.state === 'recording'} title={voice.detail} onClick={() => void (active ? runtime.audio.stopVoice() : runtime.audio.read(text))}>{active ? '停止朗读' : '朗读'}</button>;
}
