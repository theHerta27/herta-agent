import { expect, it } from 'vitest';
import { readHistory, readSessions } from '../../src/state/history-view';
import type { MessageRecord, SessionPage, SessionRecord } from '../../shared/contracts';

it('reads all history pages and keeps repeated text with different message IDs', async () => {
  const records = Array.from({ length: 103 }, (_, i) => ({
    message_id: 'm' + i, session_id: 's', run_id: 'r', seq: i + 1, step: 1,
    message: { role: 'user', content: 'same', tool_calls: [], tool_call_id: null },
  } as MessageRecord));
  const result = await readHistory(async (_id, after = 0) => ({ messages: records.filter(m => m.seq > after).slice(0, 100), current_run: null } as SessionPage), 's');
  expect(result.messages).toHaveLength(103);
  expect(result.messages[102].message_id).toBe('m102');
});

it('reads more than 50 sessions and sorts by updated time, not ID', async () => {
  const sessions = Array.from({ length: 53 }, (_, i) => ({ session_id: String(i).padStart(3, '0'), updated_at: String(i).padStart(3, '0'), created_at: '' }));
  const result = await readSessions(async (after = '') => sessions.filter(s => s.session_id > after).slice(0, 50) as SessionRecord[]);
  expect(result).toHaveLength(53);
  expect(result[0].session_id).toBe('052');
});
