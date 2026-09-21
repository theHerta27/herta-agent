"""Recovery uses committed facts only, never re-executes a tool."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from herta_agent.runtime.messages import Message, ToolCall
from herta_agent.storage.models import RunConfig, StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.tools.executor import ToolResult


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "恢复 数据.sqlite3"
        self.store = SQLiteSessionStore(self.path)
        await self.store.open()
        self.addAsyncCleanup(self.store.close)

    async def run_fixture(self, run_id, *, running=True, calls=False):
        session = await self.store.create_session()
        await self.store.admit_run(
            session.session_id, run_id, Message(role="user", content="问"), RunConfig(model="fake")
        )
        if running:
            await self.store.start_run(run_id)
        if calls:
            for step in (1, 2):
                await self.store.append_message(
                    run_id,
                    uuid4().hex,
                    step,
                    Message(
                        role="assistant",
                        tool_calls=tuple(
                            ToolCall(id=key, name="never_execute", arguments="{}")
                            for key in ("a", "b")
                        ),
                    ),
                )
                for key in ("a", "b") if step == 1 else ("a",):
                    await self.store.append_message(
                        run_id,
                        uuid4().hex,
                        step,
                        Message(role="tool", tool_call_id=key, content='{"ok":true}'),
                    )
        return session.session_id

    def sql(self, statement):
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                return connection.execute(statement).fetchall()
        finally:
            connection.close()

    async def test_restart_repairs_only_pending_and_is_idempotent(self):
        sessions = [await self.run_fixture(f"r{i}", calls=True) for i in range(2)]
        await self.run_fixture("created", running=False)
        await self.run_fixture("waiting")
        before = [await self.store.load_history(s) for s in sessions]
        await self.store.close()
        await self.store.open()
        repaired = await self.store.recover_interrupted()
        self.assertEqual({r.run_id for r in repaired}, {"r0", "r1", "created", "waiting"})
        for index, sid in enumerate(sessions):
            history = await self.store.load_history(sid)
            self.assertEqual(history[:-1], before[index])
            result = ToolResult.model_validate_json(history[-1].message.content)
            self.assertEqual(result.error.code, "interrupted")
            self.assertIn("未知", result.error.message)
            self.assertEqual(history[-1].message.tool_call_id, "b")
            self.assertEqual(history[-1].step, 2)
        snapshot = [await self.store.load_history(s) for s in sessions]
        self.assertEqual(await self.store.recover_interrupted(), ())
        self.assertEqual(snapshot, [await self.store.load_history(s) for s in sessions])
        for run in repaired:
            self.assertEqual(await self.store.get_run(run.run_id), run)
            self.assertEqual(run.status, "interrupted")
            self.assertIsNotNone(run.ended_at)
        for sid in sessions:
            await self.store.admit_run(
                sid, uuid4().hex, Message(role="user", content="继续"), RunConfig(model="fake")
            )

    async def test_cancel_and_failure_close_pending_atomically(self):
        for status in ("cancelled", "failed"):
            sid = await self.run_fixture(status, calls=True)
            run = await self.store.finish_run(status, status, steps=2)
            self.assertEqual(run.status, status)
            history = await self.store.load_history(sid)
            result = ToolResult.model_validate_json(history[-1].message.content)
            self.assertEqual(result.error.code, status)
            self.assertEqual(history[-1].message.tool_call_id, "b")
            with self.assertRaises(StoreError):
                await self.store.finish_run(status, status, steps=2)
        await self.run_fixture("early", running=False)
        self.assertEqual(
            (await self.store.finish_run("early", "cancelled", steps=0)).status, "cancelled"
        )
        self.assertEqual(await self.store.recover_interrupted(), ())

    async def test_recovery_fault_rolls_back_all_sessions_and_blocks_admission(self):
        sid = await self.run_fixture("a", calls=True)
        await self.run_fixture("z", calls=True)
        other = await self.store.create_session()
        before = self.sql("SELECT * FROM messages ORDER BY message_id")
        self.sql(
            "CREATE TRIGGER stop_recovery BEFORE UPDATE OF status ON runs "
            "WHEN NEW.run_id = 'z' BEGIN SELECT RAISE(ABORT, 'fault'); END"
        )
        with self.assertRaises(StoreError):
            await self.store.recover_interrupted()
        self.assertEqual(self.sql("SELECT * FROM messages ORDER BY message_id"), before)
        self.assertEqual(
            self.sql("SELECT status FROM runs ORDER BY run_id"), [("running",), ("running",)]
        )
        with self.assertRaises(StoreError):
            await self.store.admit_run(
                other.session_id, "new", Message(role="user", content="x"), RunConfig(model="fake")
            )
        self.assertEqual(len(await self.store.load_history(sid)), 6)

    async def test_corrupt_pairing_fails_without_repair(self):
        await self.run_fixture("bad", calls=True)
        self.sql("DELETE FROM messages WHERE seq=2")
        before = self.sql("SELECT * FROM messages ORDER BY seq")
        with self.assertRaises(StoreError):
            await self.store.recover_interrupted()
        self.assertEqual(self.sql("SELECT * FROM messages ORDER BY seq"), before)
        self.assertEqual((await self.store.get_run("bad")).status, "running")

    async def test_abort_fault_preserves_history_and_rejects_partial(self):
        sid = await self.run_fixture("r", calls=True)
        before = await self.store.load_history(sid)
        self.sql(
            "CREATE TRIGGER stop_abort BEFORE UPDATE OF status ON runs "
            "WHEN NEW.status = 'failed' BEGIN SELECT RAISE(ABORT, 'fault'); END"
        )
        with self.assertRaises(StoreError):
            await self.store.finish_run("r", "failed", steps=2)
        self.assertEqual(await self.store.load_history(sid), before)
        self.assertEqual((await self.store.get_run("r")).status, "running")
        with self.assertRaises(StoreError):
            await self.store.finish_run("r", "cancelled", steps=2, final_message=before[-1])

    async def test_restart_requires_recovery_before_new_admission(self):
        await self.run_fixture("old", running=False)
        other = await self.store.create_session()
        await self.store.close()
        await self.store.open()
        with self.assertRaises(StoreError):
            await self.store.admit_run(
                other.session_id, "new", Message(role="user", content="x"), RunConfig(model="fake")
            )
        await self.store.recover_interrupted()
        await self.store.admit_run(
            other.session_id, "new", Message(role="user", content="x"), RunConfig(model="fake")
        )
