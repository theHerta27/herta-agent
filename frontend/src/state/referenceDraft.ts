export type DraftReference = { header: string; body: string };
export const MAX_CHAT_CHARS = 10000;

export function appendReferenceDraft(existing: string, input: DraftReference | string): string {
  const reference = typeof input === 'string' ? { header: '', body: input } : input;
  const prefix = (existing ? existing + '\n\n' : '') + (reference.header ? reference.header + '\n\n' : '');
  const remaining = MAX_CHAT_CHARS - prefix.length;
  if (reference.body.length <= remaining) return prefix + reference.body;
  const notice = '\n（已按当前草稿余量截取，剩余内容请分段加入。）';
  if (remaining - notice.length < 256) throw new Error('当前草稿空间不足，请先发送或缩短草稿，再分段加入资料。');
  return prefix + reference.body.slice(0, remaining - notice.length) + notice;
}
