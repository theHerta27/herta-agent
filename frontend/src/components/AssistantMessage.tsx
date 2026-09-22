import { useState } from 'react';
import Markdown from 'react-markdown';
import avatar from '../assets/herta/avatar/herta-avatar.png';

export function AssistantMessage({ text }: { text: string }) {
  const [failed, setFailed] = useState(false);
  return <div className="message assistant-message"><div className="assistant-label">
    {failed ? <span className="avatar avatar-fallback">H</span> : <img className="avatar" src={avatar} alt="" onError={() => setFailed(true)} />} Herta
  </div><div className="markdown"><Markdown skipHtml components={{
    img: () => null,
    a: ({ children }) => <span>{children}</span>,
  }}>{text}</Markdown></div></div>;
}
