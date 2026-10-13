import type { FileJob, FilePlan, WorkspaceBridge } from '../../shared/workspace-contracts';
import type { ToolActivity } from './tool-activity';

export interface NoteProposal { rootId: string; planId: string; text: string }
export type NoteVerified = (sessionId: string, plan: FilePlan) => Promise<boolean>;

export function noteProposal(tool: ToolActivity): NoteProposal | null {
  if (tool.name !== 'propose_workspace_note' || tool.state !== 'completed') return null;
  const envelope = tool.result as { ok?: boolean; data?: Record<string, unknown> } | undefined;
  const data = envelope?.data;
  if (!envelope?.ok || !data || typeof data.root_id !== 'string' || typeof data.plan_id !== 'string' || typeof data.text_preview !== 'string' || data.text_preview.length > 10000) return null;
  return { rootId: data.root_id, planId: data.plan_id, text: data.text_preview };
}

async function hash(text: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
}

export async function loadNotePlan(bridge: WorkspaceBridge, proposal: NoteProposal): Promise<{ plan: FilePlan; job: FileJob | null }> {
  const state = await bridge.plan(proposal.planId);
  const plan = state.plan;
  if (plan.id !== proposal.planId || plan.root_id !== proposal.rootId) throw new Error('笔记方案不在当前共享目录中，请重新生成预览。');
  const outputs = plan.operations.filter(op => op.kind === 'publish');
  if (outputs.length !== 1 || plan.operations.some(op => !['mkdir', 'publish'].includes(op.kind)) || outputs[0].sha256 !== await hash(proposal.text)) throw new Error('笔记预览与后端暂存内容不一致，不能确认保存。');
  return state;
}

export async function noteResult(bridge: WorkspaceBridge, state: { plan: FilePlan; job: FileJob | null }) {
  const { plan, job } = state;
  if (job?.status !== 'completed') return { job, preview: undefined };
  const output = plan.operations.find(op => op.kind === 'publish')!;
  const preview = await bridge.read(plan.root_id, output.target, true);
  if (!preview.source_hash || preview.source_hash !== output.sha256) throw new Error('执行曾完成，但当前目标内容已变化或无法完整核对，请重新读取。');
  return { job, preview };
}
