import type { DocumentPreview } from './workspace-contracts';

export interface Task { id: string; title: string; notes: string; due_at: string | null; repeat: 'once' | 'daily' | 'weekly'; remind: boolean; reminder_id: string | null; goal_id: string | null; status: 'open' | 'completed' | 'cancelled'; revision: number; created_at: string }
export interface Goal { id: string; title: string; notes: string; deadline: string | null; status: 'active' | 'completed' | 'cancelled'; revision: number; total_tasks: number; completed_tasks: number }
export interface LearningMaterial { id: string; title: string; root_id: string | null; path: string; notes: string; progress: number; review_count: number; review_at: string; revision: number }
export type TaskRole = 'default' | 'tutor' | 'interviewer' | 'recite' | 'review';
export interface ProductivitySnapshot { tasks: Task[]; goals: Goal[]; materials: LearningMaterial[]; reviews: LearningMaterial[]; role: TaskRole; timezone: string }
export interface RecitationResult { missing: string[]; added: string[]; character_match: number; note: string }
export type ProductivityAction =
  | { kind: 'create_task'; value: { title: string; notes?: string; due_at?: string | null; repeat?: Task['repeat']; remind?: boolean; goal_id?: string | null; request_id?: string } }
  | { kind: 'task'; id: string; value: { action: 'complete' | 'postpone' | 'cancel' | 'reopen' | 'edit'; revision: number; due_at?: string | null; title?: string; notes?: string } }
  | { kind: 'create_goal'; value: { title: string; notes?: string; deadline?: string | null } }
  | { kind: 'goal'; id: string; value: { status: Goal['status']; revision: number } }
  | { kind: 'material'; value: { title: string; root_id?: string | null; path?: string; notes?: string } }
  | { kind: 'material_progress'; id: string; value: { progress: number; notes: string; revision: number } }
  | { kind: 'review'; id: string; value: { revision: number } }
  | { kind: 'role'; value: { role: TaskRole } }
  | { kind: 'recitation'; value: { expected: string; transcript: string } };
export interface ProductivityBridge {
  snapshot(): Promise<ProductivitySnapshot>;
  action(value: ProductivityAction): Promise<unknown>;
  material(id: string): Promise<DocumentPreview>;
  history(id: string): Promise<{ action: string; due_at: string | null; created_at: string }[]>;
}
