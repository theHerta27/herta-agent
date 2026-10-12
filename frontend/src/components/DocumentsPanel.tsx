import { useEffect, useRef, useState } from 'react';
import type { DocumentPreview, DocumentTransform, FilePlan, KnowledgeResults, WorkspaceRoot } from '../../shared/workspace-contracts';
import type { DraftReference } from '../state/referenceDraft';

const bridge = window.herta.workspace;
export function DocumentsPanel({ root, selected, onPlan, onDraft }: { root: WorkspaceRoot; selected: string[]; onPlan: (plan: FilePlan) => void; onDraft: (text: DraftReference | string) => void }) {
  const live = useRef(true);
  const [document, setDocument] = useState<DocumentPreview>(), [shown, setShown] = useState(100);
  const [semantic, setSemantic] = useState(true), [query, setQuery] = useState(''), [results, setResults] = useState<KnowledgeResults>();
  const [indexed, setIndexed] = useState<{ path: string; chunks: number }[]>([]);
  const [vault, setVault] = useState<string | null>(null), [text, setText] = useState(''), [notePath, setNotePath] = useState('学习/新笔记.md');
  const [kind, setKind] = useState<DocumentTransform['kind']>('merge'), [target, setTarget] = useState('成果/整理.pdf'), [pages, setPages] = useState('1'), [rotation, setRotation] = useState(90);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    live.current = true;
    void bridge.documentSettings().then(next => { if (live.current) setVault(next.vault_root_id); }).catch(() => { if (live.current) setError('笔记目录配置读取失败。'); });
    void bridge.indexedDocuments(root.id).then(next => { if (live.current) setIndexed(next); }).catch(() => { if (live.current) setError('资料索引读取失败。'); });
    return () => { live.current = false; };
  }, [root.id]);
  const work = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); } catch (cause) { if (live.current) setError(String(cause)); }
    finally {
      try { const next = await bridge.indexedDocuments(root.id); if (live.current) setIndexed(next); } catch { /* Keep the action error visible. */ }
      if (live.current) setBusy(false);
    }
  };
  const materials = selected.filter(path => /\.(pdf|docx|txt|md)$/i.test(path));
  const draft = (summarize = false) => {
    if (!document) return;
    try {
      onDraft({ header: `${summarize ? '请根据以下有引用的资料整理学习笔记，列出核心概念、例子、待复习问题，保留原引用。' : '以下是我主动分享的文档资料。'}\n资料：${root.label}/${document.path}${document.truncated ? '（正文抽取已截断）' : ''}`, body: document.segments.map(s => `[${s.citation}]\n${s.text}`).join('\n\n') });
    } catch (cause) { setError(String(cause)); }
  };
  return <section className="documents-panel" aria-label="文档与个人知识">
    <div className="file-actions-heading"><h3>文档与个人知识</h3><span>本地处理 · 引用保留</span></div>
    {indexed.length > 0 && <details><summary>已索引资料 · {indexed.length} 份</summary>{indexed.map(item => <p key={item.path}>{item.path} · {item.chunks} 片段 <button disabled={busy} onClick={() => void work(() => bridge.forgetDocument(root.id, item.path))}>移除索引</button></p>)}</details>}
    <p className="file-note">勾选资料后阅读或建立索引。PDF按页、DOCX按段落引用；扫描件不冒充正文。索引只用本地模型，目录共享后聊天才可读取。</p>
    <div className="document-actions"><button disabled={busy || selected.length !== 1 || materials.length !== 1} onClick={() => void work(async () => { const next = await bridge.document(root.id, materials[0]); if (live.current) { setDocument(next); setShown(100); } })}>阅读选中文档</button><label><input type="checkbox" checked={semantic} onChange={e => setSemantic(e.target.checked)} disabled={busy} />本地语义检索</label><button disabled={busy || !materials.length} onClick={() => void work(async () => { const next = await bridge.indexDocuments(root.id, materials, semantic); if (live.current) setMessage(`${next.documents} 份资料 · ${next.chunks} 个片段 · ${next.mode === 'local_bge' ? '本地语义索引' : '文字索引'}${next.warnings.length ? `：${next.warnings.join('；')}` : ''}`); })}>建立资料索引</button></div>
    {document && <div className="document-preview"><h4>{document.path} · {document.units} 个原文单元</h4>{document.warnings.map((warning, i) => <p className="file-note" key={i}>{warning}</p>)}<div className="document-body">{document.segments.slice(0, shown).map((segment, i) => <article key={i}><small>{segment.citation}</small><pre>{segment.text}</pre></article>)}</div>{document.segments.length > shown && <button onClick={() => setShown(n => n + 100)}>再显示100段</button>}<div className="document-actions"><button disabled={busy} onClick={() => draft()}>文档加入聊天草稿</button><button disabled={busy} onClick={() => draft(true)}>请求整理学习笔记</button><button onClick={() => {
      setText(`# ${document.path.replace(/\.[^.]+$/, '')}\n\n## 原文摘录\n\n${document.segments.slice(0, 10).map(s => `> ${s.text.slice(0, 1000).replaceAll('\n', '\n> ')}\n\n来源：${s.citation}`).join('\n\n')}\n\n## 我的理解\n\n\n## 待复习问题\n\n- \n`);
      setNotePath(`学习/${document.path.split('/').pop()!.replace(/\.[^.]+$/, '')}.md`);
    }}>生成摘录笔记草稿</button></div><p className="file-note">聊天草稿可编辑，点击发送才会交给配置的聊天服务。摘录草稿保留原文，供你补充理解。</p></div>}
    <form className="file-search" onSubmit={e => { e.preventDefault(); void work(async () => { const next = await bridge.knowledge(root.id, query, semantic); if (live.current) setResults(next); }); }}><input aria-label="检索个人资料" value={query} maxLength={200} placeholder="查找已索引的资料内容" onChange={e => setQuery(e.target.value)} /><button disabled={busy || !query.trim()}>检索资料</button></form>
    {results && <div className="knowledge-results">{results.warning && <p className="file-note">{results.warning}</p>}{!results.results.length && <p className="file-note">未找到当前有效的片段。请先建立索引，文件修改后需重新索引。</p>}{results.results.map((result, i) => <article key={i}><small>{result.citation}</small><p>{result.text}</p></article>)}{results.results.length > 0 && <button onClick={() => onDraft(`我主动分享以下个人资料片段：\n\n${results.results.map(r => `[${r.citation}]\n${r.text}`).join('\n\n')}`)}>检索结果加入聊天草稿</button>}</div>}
    <details className="document-conversion"><summary>PDF操作与DOCX转换</summary><p className="file-note">处理勾选的文件，生成新PDF；审阅保存方案后才写入目录。</p><form className="file-action-form" onSubmit={e => { e.preventDefault(); void work(async () => { const next = await bridge.transform(root.id, { paths: selected, kind, target, pages: kind === 'split' ? pages.split(/[,，\s]+/).filter(Boolean).map(Number) : [], rotation: kind === 'rotate' ? rotation : 0 }); if (live.current) onPlan(next); }); }}><select aria-label="文档转换" value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="merge">合并PDF</option><option value="split">提取PDF页面</option><option value="rotate">旋转PDF</option><option value="images">图片转PDF</option><option value="docx_pdf">DOCX转PDF</option></select><input aria-label="转换保存位置" value={target} maxLength={240} onChange={e => setTarget(e.target.value)} />{kind === 'split' && <input aria-label="提取页码" value={pages} onChange={e => setPages(e.target.value)} placeholder="1,3,5" />}{kind === 'rotate' && <select aria-label="旋转角度" value={rotation} onChange={e => setRotation(Number(e.target.value))}><option value={90}>90°</option><option value={180}>180°</option><option value={270}>270°</option></select>}<button disabled={busy || !selected.length || !target.trim()}>生成转换保存方案</button></form></details>
    <div className="document-notes"><h4>学习笔记</h4>{vault === root.id ? <p className="file-note">此目录已绑定为笔记Vault。</p> : <button disabled={busy} onClick={() => void work(async () => { const next = await bridge.bindVault(root.id); if (live.current) setVault(next.vault_root_id); })}>绑定此目录为笔记Vault</button>}<input aria-label="笔记保存位置" value={notePath} maxLength={240} onChange={e => setNotePath(e.target.value)} /><textarea aria-label="学习笔记草稿" rows={7} value={text} maxLength={100000} placeholder="编辑Markdown笔记，或粘贴聊天中整理的学习成果。" onChange={e => setText(e.target.value)} /><button disabled={busy || vault !== root.id || !text.trim() || !notePath.trim()} onClick={() => void work(async () => { const next = await bridge.note(root.id, notePath, text); if (live.current) onPlan(next); })}>预览保存笔记</button></div>
    {busy && <p aria-live="polite">正在本地处理…</p>}{message && <p aria-live="polite">{message}</p>}{error && <p className="error" role="alert">{error}</p>}
  </section>;
}
