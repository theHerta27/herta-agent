import { describe, expect, it } from 'vitest';
import { appendReferenceDraft } from '../../src/state/referenceDraft';

describe('document draft budget', () => {
  it('includes existing text, prompt, citations and truncation notice within the chat limit', () => {
    const existing = '已有草稿'.repeat(1500);
    const header = '请整理学习笔记。资料：资料目录/长材料.txt';
    const result = appendReferenceDraft(existing, { header, body: '[长材料.txt#段落1]\n' + '长文内容'.repeat(5000) });
    expect(result.startsWith(existing + '\n\n' + header)).toBe(true);
    expect(result).toContain('[长材料.txt#段落1]');
    expect(result).toContain('已按当前草稿余量截取');
    expect(result.length).toBeLessThanOrEqual(10000);
  });
  it('keeps short material complete and refuses to replace a nearly full draft', () => {
    expect(appendReferenceDraft('原文', { header: '资料', body: '完整内容' })).toBe('原文\n\n资料\n\n完整内容');
    expect(() => appendReferenceDraft('x'.repeat(9950), { header: '资料', body: '内容'.repeat(6000) })).toThrow('分段');
  });
});
