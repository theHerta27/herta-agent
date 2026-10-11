import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Recorder } from '../audio/recorder';
import type { CompanionRuntime } from '../state/companion-runtime';

export function VoiceInput({ runtime, disabled, sessionKey, onText }: { runtime: CompanionRuntime; disabled: boolean; sessionKey: string; onText: (text: string) => void }) {
  const { voice } = useSyncExternalStore(runtime.subscribe, runtime.snapshot);
  const [state, setState] = useState<'idle' | 'requesting' | 'recording' | 'recognizing'>('idle');
  const [error, setError] = useState('');
  const recorder = useRef(new Recorder());
  const generation = useRef(0);
  const currentSession = useRef(sessionKey); currentSession.current = sessionKey;
  useLayoutEffect(() => {
    setState('idle'); setError('');
    const current = recorder.current;
    return () => { ++generation.current; void current.cancel(); void runtime.audio.stopVoice(); };
  }, [runtime, sessionKey, disabled]);
  const cancel = async () => { ++generation.current; await recorder.current.cancel(); await runtime.audio.stopVoice(); setState('idle'); };
  const finish = async () => {
    const token = ++generation.current;
    const session = sessionKey;
    setState('recognizing');
    try {
      const wav = await recorder.current.stop();
      if (generation.current !== token || currentSession.current !== session) return;
      runtime.audio.endRecording();
      const result = await runtime.bridge.transcribe(wav);
      if (generation.current === token && currentSession.current === session) { if (result.text.trim()) onText(result.text); else setError('没有识别到清楚的语音，请重试。'); }
    } catch { if (generation.current === token) setError('识别未完成，请检查本地模型或重新录音。'); }
    finally { if (generation.current === token) { runtime.audio.endRecording(); setState('idle'); } }
  };
  const start = async () => {
    const token = ++generation.current; setState('requesting'); setError('');
    try {
      if (!(await runtime.audio.beginRecording())) { if (token === generation.current) setState('idle'); return; }
      if (token !== generation.current) { runtime.audio.endRecording(); return; }
      const started = await recorder.current.start(() => void finish());
      if (started && token === generation.current) setState('recording');
      else if (started) { await recorder.current.cancel(); runtime.audio.endRecording(); }
    } catch { await recorder.current.cancel(); if (token === generation.current) { runtime.audio.endRecording(); setError('无法录音。请在系统中允许 Herta 使用麦克风。'); setState('idle'); } }
  };
  return <div className="voice-input"><button type="button" disabled={state === 'idle' && (disabled || !voice.asr)} title={voice.asr ? '录音后可编辑文字，最长60秒' : voice.detail} onClick={() => void (state === 'idle' ? start() : state === 'recording' ? finish() : cancel())}>
    {({ idle: '录音', requesting: '取消录音', recording: '结束录音', recognizing: '取消识别' })[state]}</button>
    <small>{state === 'recording' ? '正在录音…最长60秒' : state === 'recognizing' ? '本地识别中…' : error || '识别后可编辑，再发送'}</small></div>;
}
