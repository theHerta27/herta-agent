import hero from '../assets/herta/welcome/herta-welcome-bust.png';

export function WelcomeView({ onExample }: { onExample: (text: string) => void }) {
  return <section className="welcome">
    <img className="hero" src={hero} alt="" onError={event => { event.currentTarget.style.visibility = 'hidden'; }} />
    <h1>Herta</h1><p>把你的问题带来。</p>
    <div className="examples"><button onClick={() => onExample('大黑塔和黑塔人偶是什么关系？')}>大黑塔和人偶的关系</button><button onClick={() => onExample('请查阅资料，介绍大黑塔的故事。')}>聊聊她的故事</button></div>
  </section>;
}
