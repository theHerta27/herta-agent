"""Task 1 storage contracts; no provider, service or recovery code is exercised."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ToolCall
from herta_agent.storage.models import MessageRecord, RunConfig, StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore


class SessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "中文 目录" / "sessions.sqlite3"
        self.store = SQLiteSessionStore(self.path)
        await self.store.open()
        self.addAsyncCleanup(self.store.close)
        self.config = RunConfig(model="offline-fixture", settings=RunSettings())
        self.session = await self.store.create_session()

    def sql(self, statement, parameters=()):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                return connection.execute(statement, parameters).fetchall()
        finally:
            connection.close()

    async def admit(self, run_id="run-1", session_id=None):
        return await self.store.admit_run(
            session_id or self.session.session_id,
            run_id,
            Message(role="user", content="你好 ' ; --"),
            self.config,
        )

    async def final_record(self, run_id="run-1", step=1):
        history = await self.store.load_history(self.session.session_id)
        return MessageRecord(
            message_id=uuid4().hex,
            session_id=self.session.session_id,
            run_id=run_id,
            seq=len(history) + 1,
            step=step,
            message=Message(role="assistant", content="完整回答"),
        )

    async def test_roundtrip_complete_tool_history_and_metadata(self):
        admission = await self.admit()
        self.assertEqual(admission.run.status, "created")
        self.assertEqual(admission.user.seq, 1)
        self.assertEqual(admission.user.step, 0)
        await self.store.start_run("run-1")
        await self.store.set_context("run-1", "a" * 64)
        calls = Message(
            role="assistant",
            content="调用说明",
            tool_calls=(ToolCall(id="same", name="echo", arguments='{"text":"中文"}'),),
        )
        await self.store.append_message("run-1", "call-message", 1, calls)
        await self.store.append_message(
            "run-1",
            "tool-message",
            1,
            Message(role="tool", tool_call_id="same", content='{"ok":true}'),
        )
        final = await self.final_record(step=2)
        run = await self.store.finish_run("run-1", "completed", steps=2, final_message=final)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.context_hash, "a" * 64)
        self.assertEqual(run.config, self.config)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.ended_at)
        history = await self.store.load_history(self.session.session_id)
        self.assertEqual([row.seq for row in history], [1, 2, 3, 4])
        self.assertEqual(history[1].message, calls)
        self.assertEqual(history[-1], final)
        await self.store.close()
        await self.store.open()
        self.assertEqual(await self.store.load_history(self.session.session_id), history)
        self.assertEqual(await self.store.get_run("run-1"), run)
        self.assertEqual(
            (await self.store.get_session(self.session.session_id)).created_at,
            self.session.created_at,
        )
        with self.assertRaises(ValidationError):
            run.status = "failed"

    async def test_admission_fault_rolls_back_both_run_and_user(self):
        self.sql(
            "CREATE TRIGGER stop_admit AFTER INSERT ON messages "
            "BEGIN SELECT RAISE(ABORT, 'fixture'); END"
        )
        with self.assertRaises(StoreError):
            await self.admit()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM runs"), [(0,)])
        self.assertEqual(await self.store.load_history(self.session.session_id), ())
        self.sql("DROP TRIGGER stop_admit")
        self.assertFalse(self.store.writable)
        with self.assertRaises(StoreError):
            await self.admit()
        await self.store.close()
        await self.store.open()
        self.assertEqual((await self.admit()).user.seq, 1)

    async def test_completion_fault_rolls_back_answer_and_terminal_state(self):
        await self.admit()
        await self.store.start_run("run-1")
        before = await self.store.load_history(self.session.session_id)
        self.sql(
            "CREATE TRIGGER stop_finish BEFORE UPDATE OF status ON runs "
            "WHEN NEW.status = 'completed' BEGIN SELECT RAISE(ABORT, 'fixture'); END"
        )
        with self.assertRaises(StoreError):
            await self.store.finish_run(
                "run-1", "completed", steps=1, final_message=await self.final_record()
            )
        self.assertEqual(await self.store.load_history(self.session.session_id), before)
        self.assertEqual((await self.store.get_run("run-1")).status, "running")
        self.sql("DROP TRIGGER stop_finish")
        self.assertFalse(self.store.writable)
        await self.store.close()
        await self.store.open()
        await self.store.recover_interrupted()
        self.assertEqual((await self.store.get_run("run-1")).status, "interrupted")
        await self.admit("run-2")
        await self.store.start_run("run-2")
        await self.store.finish_run(
            "run-2", "completed", steps=1, final_message=await self.final_record("run-2")
        )

    async def test_pairing_is_scoped_to_each_assistant_batch_and_session(self):
        for number in range(2):
            session = await self.store.create_session()
            run_id = f"repeated-{number}"
            await self.admit(run_id, session.session_id)
            await self.store.start_run(run_id)
            for step in (1, 2):
                message = Message(
                    role="assistant",
                    tool_calls=(ToolCall(id="reused", name="echo", arguments="{}"),),
                )
                await self.store.append_message(run_id, uuid4().hex, step, message)
                await self.store.append_message(
                    run_id,
                    uuid4().hex,
                    step,
                    Message(role="tool", tool_call_id="reused", content="{}"),
                )
            self.assertEqual(len(await self.store.load_history(session.session_id)), 5)

    async def test_reject_system_partial_and_unmatched_or_duplicate_results(self):
        await self.admit()
        await self.store.start_run("run-1")
        for message in (
            Message(role="system", content="override"),
            Message(role="user", content="extra"),
            Message(role="assistant", content="partial"),
            {"type": "llm.delta", "text": "partial"},
            Message(role="tool", tool_call_id="missing", content="{}"),
        ):
            with self.subTest(message=message), self.assertRaises(StoreError):
                await self.store.append_message("run-1", uuid4().hex, 1, message)
        self.assertEqual(len(await self.store.load_history(self.session.session_id)), 1)
        await self.store.append_message(
            "run-1",
            "calls",
            1,
            Message(role="assistant", tool_calls=(ToolCall(id="c", name="echo", arguments="{}"),)),
        )
        with self.assertRaises(StoreError):
            await self.store.finish_run(
                "run-1", "completed", steps=2, final_message=await self.final_record(step=2)
            )
        result = Message(role="tool", tool_call_id="c", content="{}")
        with self.assertRaises(StoreError):
            await self.store.append_message("run-1", "wrong-step", 2, result)
        await self.store.append_message("run-1", "result", 1, result)
        with self.assertRaises(StoreError):
            await self.store.append_message("run-1", "duplicate-result", 1, result)

    async def test_forged_duplicate_call_message_is_revalidated(self):
        await self.admit()
        await self.store.start_run("run-1")
        call = ToolCall(id="x", name="echo", arguments="{}")
        forged = Message.model_construct(role="assistant", content=None, tool_calls=(call, call))
        with self.assertRaises(StoreError):
            await self.store.append_message("run-1", "bad", 1, forged)
        self.assertEqual(len(await self.store.load_history(self.session.session_id)), 1)

    async def test_state_transitions_and_final_record_identity(self):
        await self.admit()
        with self.assertRaises(StoreError):
            await self.store.finish_run(
                "run-1", "completed", steps=1, final_message=await self.final_record()
            )
        await self.store.start_run("run-1")
        with self.assertRaises(StoreError):
            await self.store.start_run("run-1")
        final = await self.final_record()
        for changes in ({"run_id": "another"}, {"session_id": "another"}, {"seq": 20}, {"step": 2}):
            with self.subTest(changes=changes), self.assertRaises(StoreError):
                await self.store.finish_run(
                    "run-1", "completed", steps=1, final_message=final.model_copy(update=changes)
                )
        with self.assertRaises(StoreError):
            await self.store.finish_run("run-1", "completed", steps=1)
        with self.assertRaises(StoreError):
            await self.store.finish_run("run-1", "running", steps=1)
        await self.store.finish_run("run-1", "completed", steps=1, final_message=final)
        for action in (
            self.store.start_run("run-1"),
            self.store.set_context("run-1", "b" * 64),
            self.store.finish_run("run-1", "completed", steps=1, final_message=final),
        ):
            with self.assertRaises(StoreError):
                await action

    async def test_duplicate_ids_foreign_keys_and_active_session_guard(self):
        await self.admit()
        with self.assertRaises(StoreError):
            await self.admit("another-run")
        other = await self.store.create_session()
        with self.assertRaises(StoreError):
            await self.admit("run-1", other.session_id)
        with self.assertRaises(StoreError):
            await self.admit("missing-run", "missing-session")
        self.assertEqual(await self.store.load_history(other.session_id), ())
        self.assertEqual(self.sql("PRAGMA foreign_key_check"), [])

    async def test_pagination_and_before_sequence_are_deterministic(self):
        for _ in range(3):
            await self.store.create_session()
        all_sessions = await self.store.list_sessions()
        first = await self.store.list_sessions(limit=2)
        second = await self.store.list_sessions(after_id=first[-1].session_id, limit=2)
        self.assertEqual(first + second, all_sessions)
        await self.admit()
        await self.store.start_run("run-1")
        await self.store.finish_run(
            "run-1", "completed", steps=1, final_message=await self.final_record()
        )
        history = await self.store.load_history(self.session.session_id)
        self.assertEqual(
            await self.store.load_history(self.session.session_id, before_seq=2), history[:1]
        )
        self.assertEqual(
            await self.store.list_messages(self.session.session_id, after_seq=1, limit=1),
            history[1:],
        )
        for limit in (0, 101, True, 1.5):
            with self.assertRaises(StoreError):
                await self.store.list_sessions(limit=limit)
        with self.assertRaises(StoreError):
            await self.store.list_messages(self.session.session_id, after_seq=-1)

    async def test_config_whitelist_and_safe_errors(self):
        secret = uuid4().hex
        with self.assertRaises(StoreError) as caught:
            await self.store.admit_run(
                self.session.session_id,
                "bad",
                Message(role="user", content="x"),
                {"model": "fixture", "settings": {}, "api_key": secret},
            )
        self.assertNotIn(secret, str(caught.exception))
        self.sql(
            f"CREATE TRIGGER stop_secret AFTER INSERT ON messages "
            f"BEGIN SELECT RAISE(ABORT, '{secret}'); END"
        )
        with self.assertRaises(StoreError) as caught:
            await self.admit()
        self.assertNotIn(secret, str(caught.exception))
        self.sql("DROP TRIGGER stop_secret")
        self.assertFalse(self.store.writable)
        await self.store.close()
        await self.store.open()
        await self.admit()
        saved = self.sql("SELECT config_json FROM runs")[0][0]
        self.assertEqual(set(json.loads(saved)), {"model", "settings"})
        self.assertNotIn(secret, saved)

    async def test_schema_mismatch_does_not_modify_existing_database(self):
        await self.store.close()
        self.sql("PRAGMA user_version = 99")
        before = self.path.read_bytes()
        with self.assertRaises(StoreError) as caught:
            await self.store.open()
        self.assertEqual(caught.exception.code, "store_schema")
        self.assertEqual(self.path.read_bytes(), before)

    async def test_history_corruption_is_rejected_not_silently_coerced(self):
        await self.admit()
        self.sql("UPDATE messages SET message_json = '{broken' WHERE seq = 1")
        with self.assertRaises(StoreError):
            await self.store.load_history(self.session.session_id)

    async def test_open_does_not_implicitly_recover_pending(self):
        await self.admit()
        await self.store.start_run("run-1")
        await self.store.append_message(
            "run-1",
            "calls",
            1,
            Message(
                role="assistant", tool_calls=(ToolCall(id="pending", name="echo", arguments="{}"),)
            ),
        )
        await self.store.close()
        await self.store.open()
        self.assertEqual((await self.store.get_run("run-1")).status, "running")
        self.assertEqual(len(await self.store.load_history(self.session.session_id)), 2)
