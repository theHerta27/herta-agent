import type { DesktopBridge, MessageRecord, RunRecord, SessionRecord } from '../../shared/contracts';

export async function readHistory(get: DesktopBridge['getSession'], id: string) {
  const messages = new Map<string, MessageRecord>();
  let after = 0;
  let currentRun: RunRecord | null = null;
  while (true) {
    const page = await get(id, after, 100);
    currentRun = page.current_run;
    for (const record of page.messages) messages.set(record.message_id, record);
    if (page.messages.length < 100) break;
    const next = page.messages.at(-1)!.seq;
    if (next <= after) throw new Error('invalid_page');
    after = next;
  }
  return { messages: [...messages.values()].sort((a, b) => a.seq - b.seq), currentRun };
}

export async function readSessions(get: DesktopBridge['listSessions']): Promise<SessionRecord[]> {
  const sessions: SessionRecord[] = [];
  let after: string | undefined;
  while (true) {
    const page = await get(after, 50);
    sessions.push(...page);
    if (page.length < 50) break;
    const next = page.at(-1)!.session_id;
    if (next === after) throw new Error('invalid_page');
    after = next;
  }
  return sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export async function mapFour<T>(items: T[], visit: (item: T) => Promise<void>) {
  let index = 0;
  await Promise.all(Array.from({ length: Math.min(4, items.length) }, async () => {
    while (index < items.length) await visit(items[index++]);
  }));
}
