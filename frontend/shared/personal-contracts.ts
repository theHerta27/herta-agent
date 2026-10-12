import type { VoiceStatus } from './contracts';
export interface PersonalMemory { id: string; text: string; status: 'pending' | 'approved' | 'disabled'; revision: number; source: string }
export interface PersonalSkill { id: string; title: string; instructions: string; status: 'pending' | 'approved'; enabled: boolean; revision: number; source: { kind: string; task_id?: string }; created_at: string }
export interface PersonalSnapshot { persona: { text: string; revision: number }; base_persona: string; voice: { provider: 'piper' | 'the_herta'; emotion: string }; speech: VoiceStatus & { providers: { piper: boolean; the_herta: boolean } }; memories: PersonalMemory[]; skills: PersonalSkill[] }
export interface PersonalAction { kind: 'persona' | 'voice' | 'memory' | 'skill' | 'draft' | 'from_task'; id?: string; revision?: number; action?: 'edit' | 'approve' | 'disable' | 'enable' | 'delete'; text?: string; title?: string; provider?: 'piper' | 'the_herta'; emotion?: string }
export interface PersonalBridge { snapshot(): Promise<PersonalSnapshot>; action(value: PersonalAction): Promise<unknown> }
