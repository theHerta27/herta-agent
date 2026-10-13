import { createHash } from 'node:crypto';
import { expect, test, vi } from 'vitest';
import type { FileJob, FilePlan, WorkspaceBridge } from '../../shared/workspace-contracts';
import { loadNotePlan, noteProposal, noteResult } from '../../src/state/note-task';
import type { ToolActivity } from '../../src/state/tool-activity';

const text = '# 笔记\n来源：a.md#行1\n';
const digest = createHash('sha256').update(text).digest('hex');
const plan: FilePlan = { id: 'plan', root_id: 'root', root_label: '资料', created_at: '2026-10-13T00:00:00Z', digest: 'a'.repeat(64), operations: [{ kind: 'publish', target: 'note.md', sha256: digest }], conflicts: [] };
const proposal = { rootId: 'root', planId: 'plan', text };
const job: FileJob = { id: 'job', root_id: 'root', status: 'completed', created_at: plan.created_at, plan, receipts: [], error: null };
function bridge() {
  return { plan: vi.fn().mockResolvedValue({ plan, job }), read: vi.fn().mockResolvedValue({ text, source_hash: digest }) } as unknown as WorkspaceBridge;
}

test('only successful owned note tool results become proposals', () => {
  const tool: ToolActivity = { key: 'key', step: 1, id: 'call', name: 'propose_workspace_note', state: 'completed', result: { ok: true, data: { root_id: 'root', plan_id: 'plan', text_preview: text } } };
  expect(noteProposal(tool)).toEqual(proposal);
  expect(noteProposal({ ...tool, state: 'failed' })).toBeNull();
  expect(noteProposal({ ...tool, name: 'echo' })).toBeNull();
  expect(noteProposal({ ...tool, result: { ok: true, data: { text_preview: text } } })).toBeNull();
});

test('approval loads the server plan and binds the displayed text to staged bytes', async () => {
  const client = bridge();
  expect((await loadNotePlan(client, proposal)).plan).toBe(plan);
  await expect(loadNotePlan(client, { ...proposal, text: '替换预览' })).rejects.toThrow('不一致');
  vi.mocked(client.plan).mockResolvedValue({ plan: { ...plan, operations: [...plan.operations, { kind: 'move', source: 'a.md', target: 'b.md' }] }, job });
  await expect(loadNotePlan(client, proposal)).rejects.toThrow('不一致');
});

test('revoked sharing prevents loading a plan for chat confirmation', async () => {
  const client = bridge();
  vi.mocked(client.plan).mockRejectedValue(new Error('目录未共享'));
  await expect(loadNotePlan(client, proposal)).rejects.toThrow('未共享');
  expect(client.read).not.toHaveBeenCalled();
});

test('saved result reads the actual shared file and rejects changed bytes', async () => {
  const client = bridge();
  const result = await noteResult(client, { plan, job });
  expect(result.preview?.text).toBe(text);
  expect(client.read).toHaveBeenCalledWith('root', 'note.md', true);
  vi.mocked(client.read).mockResolvedValue({ path: 'note.md', text: '后续变更', source_hash: 'b'.repeat(64), start_line: 1, truncated: false });
  await expect(noteResult(client, { plan, job })).rejects.toThrow('已变化');
});
