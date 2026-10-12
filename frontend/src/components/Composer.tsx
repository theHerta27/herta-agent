import { useLayoutEffect, useRef } from 'react';
import { shouldSend } from './composer-input';
import { MAX_CHAT_CHARS } from '../state/referenceDraft';

export function Composer({ value, onChange, onSend, onStop, busy, cancelling, disabled }: {
  value: string; onChange: (text: string) => void; onSend: () => void; onStop: () => void;
  busy: boolean; cancelling: boolean; disabled: boolean;
}) {
  const input = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (input.current) { input.current.style.height = '0px'; input.current.style.height = Math.min(180, input.current.scrollHeight) + 'px'; }
  }, [value]);
  const canSend = !busy && !disabled && !!value.trim() && value.length <= MAX_CHAT_CHARS;
  return <div className="composer-wrap">
    <form className="composer" onSubmit={event => { event.preventDefault(); if (canSend) onSend(); }}>
      <textarea ref={input} aria-label="消息" placeholder="向 Herta 提问…" value={value}
        onChange={event => onChange(event.target.value)} rows={1} disabled={disabled && !busy}
        onKeyDown={event => {
          if (shouldSend({ key: event.key, shiftKey: event.shiftKey, isComposing: event.nativeEvent.isComposing, keyCode: event.nativeEvent.keyCode })) {
            event.preventDefault(); if (canSend) onSend();
          }
        }} />
      <div className="composer-actions"><span>{value.length > 9000 ? `${value.length} / 10000` : 'Shift + Enter 换行'}</span>
        {busy ? <button type="button" className="send stop" disabled={cancelling} onClick={onStop} aria-label="停止">■ <span>{cancelling ? '正在取消' : '停止'}</span></button>
          : <button className="send" type="submit" disabled={!canSend} aria-label="发送">↑</button>}
      </div>
    </form>
    <p className="composer-note">Herta 也可能出错，请核对重要信息。</p>
  </div>;
}
