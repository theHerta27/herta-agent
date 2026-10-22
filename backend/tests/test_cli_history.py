"""CLI persistence through the existing SQLite store; all providers here are offline."""

import asyncio
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


class CLIHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()
        self.data = self.root / "state"

    def invoke(self, *args, repo=None, input_text=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("HERTA_") and key != "DEEPSEEK_API_KEY"
        }
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        return subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                "-m",
                "herta_agent",
                "--repo",
                str(repo or self.repo),
                "--data-dir",
                str(self.data),
                *args,
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=input_text,
            timeout=10,
        )

    def saved(self):
        result = self.invoke("--message", "first")
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(r"\[session=([0-9a-f]{32})\]", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        return match.group(1)

    def test_new_process_resumes_real_saved_history(self):
        session_id = self.saved()
        result = self.invoke("--resume", session_id, "--message", "second")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("第 2 轮", result.stdout)
        self.assertIn("收到：second", result.stdout)
        self.assertIn(f"[session={session_id}]", result.stdout)

    def test_list_is_local_and_does_not_create_another_session(self):
        session_id = self.saved()
        result = self.invoke("--list-sessions", "--provider", "openai")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(session_id, result.stdout)
        self.assertIn("completed", result.stdout)
        self.assertNotIn("请求 Provider", result.stdout)
        self.assertNotIn("HERTA_API_KEY", result.stderr)

    def test_resume_is_bound_to_selected_repository(self):
        session_id = self.saved()
        other = self.root / "other"
        other.mkdir()
        result = self.invoke("--resume", session_id, "--message", "second", repo=other)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("会话不存在", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_failed_turn_remains_recoverable(self):
        session_id = self.saved()
        failed = self.invoke(
            "--resume", session_id, "--demo-tools", "--max-steps", "1", "--message", "fail"
        )
        self.assertEqual(failed.returncode, 1, failed.stderr)
        result = self.invoke("--resume", session_id, "--message", "after failure")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("第 3 轮", result.stdout)
        self.assertIn("failed", self._run_statuses())

    def _run_statuses(self):
        import sqlite3

        path = next(self.data.rglob("sessions.sqlite3"))
        with closing(sqlite3.connect(path)) as connection:
            return str(connection.execute("SELECT status FROM runs").fetchall())

    def test_read_tool_messages_and_context_diagnostics_survive_restart(self):
        (self.repo / "note.md").write_text("synthetic note", encoding="utf-8")
        result = self.invoke("--demo-read-file", "note.md", "--message", "read")
        self.assertEqual(result.returncode, 0, result.stderr)
        import sqlite3

        path = next(self.data.rglob("sessions.sqlite3"))
        with closing(sqlite3.connect(path)) as connection:
            messages = connection.execute(
                "SELECT message_json FROM messages ORDER BY seq"
            ).fetchall()
            diagnostics = connection.execute("SELECT count(*) FROM context_diagnostics").fetchone()[
                0
            ]
        self.assertEqual(len(messages), 4)
        self.assertIn("synthetic note", str(messages))
        self.assertGreaterEqual(diagnostics, 2)
        self.assertIn("completed", self._run_statuses())

    def test_unknown_session_and_conflicting_options_are_safe_errors(self):
        result = self.invoke("--resume", "missing", "--message", "hello")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        conflict = self.invoke("--resume", "missing", "--no-save", "--message", "hello")
        self.assertEqual(conflict.returncode, 2, conflict.stderr)


class CLIHistoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def test_default_path_uses_localappdata_without_resolving_home(self):
        from herta_agent.cli_history import history_path
        from herta_agent.tools.coding.paths import Repository

        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.path.parent)}, clear=True):
            with patch.object(Path, "home", side_effect=RuntimeError("no home")):
                self.assertTrue(
                    history_path(Repository(self.path.parent)).is_relative_to(self.path.parent)
                )

    async def asyncSetUp(self):
        from herta_agent.cli_history import CLIHistory

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sessions.sqlite3"
        self.history = CLIHistory(self.path)
        await self.history.open()
        self.addAsyncCleanup(self.history.close)
        self.session = await self.history.session()

    async def test_second_owner_cannot_recover_live_database(self):
        from herta_agent.cli_history import CLIHistory
        from herta_agent.storage.models import StoreError

        other = CLIHistory(self.path)
        with self.assertRaises(StoreError):
            await other.open()
        await other.close()
        self.assertTrue(self.history.store.writable)

    async def test_startup_closes_pending_calls_without_executing_them(self):
        from herta_agent.runtime.messages import Message, ToolCall
        from herta_agent.storage.models import RunConfig

        store = self.history.store
        await store.admit_run(
            self.session.session_id,
            "interrupted",
            Message(role="user", content="go"),
            RunConfig(model="fixture"),
        )
        await store.start_run("interrupted")
        await store.append_message(
            "interrupted",
            "calls",
            1,
            Message(
                role="assistant",
                tool_calls=(ToolCall(id="call", name="create_file", arguments="{}"),),
            ),
        )
        await self.history.close()
        recovered = await self.history.open()
        self.assertEqual([r.status for r in recovered], ["interrupted"])
        restored = await self.history.session(self.session.session_id)
        self.assertEqual(restored.history[-1].role, "tool")
        self.assertIn("interrupted", restored.history[-1].content)
        self.assertFalse(any(p.name == "unexpected" for p in self.path.parent.iterdir()))

    async def test_model_cancellation_persists_terminal_state_and_allows_next_turn(self):
        from herta_agent.llm.demo import DemoProvider
        from herta_agent.runtime.agent import Agent

        started = asyncio.Event()

        class WaitingProvider:
            async def complete(self, messages, *, tools=()):
                started.set()
                await asyncio.sleep(30)

        task = asyncio.create_task(
            self.history.run(Agent(WaitingProvider()), self.session.session_id, "wait")
        )
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        _, _, run = await self.history.store.get_session_snapshot(self.session.session_id)
        self.assertEqual(run.status, "cancelled")
        result = await self.history.run(Agent(DemoProvider()), self.session.session_id, "next")
        self.assertIn("第 2 轮", result.reply)

    async def test_cancellation_during_admission_does_not_block_next_turn(self):
        from herta_agent.llm.demo import DemoProvider
        from herta_agent.runtime.agent import Agent

        admitted = asyncio.Event()
        original = self.history.store.admit_run

        async def delayed(*args, **kwargs):
            result = await original(*args, **kwargs)
            admitted.set()
            await asyncio.sleep(30)
            return result

        with patch.object(self.history.store, "admit_run", side_effect=delayed):
            task = asyncio.create_task(
                self.history.run(Agent(DemoProvider()), self.session.session_id, "wait")
            )
            await asyncio.wait_for(admitted.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        _, _, run = await self.history.store.get_session_snapshot(self.session.session_id)
        self.assertEqual(run.status, "cancelled")
        result = await self.history.run(Agent(DemoProvider()), self.session.session_id, "next")
        self.assertIn("第 2 轮", result.reply)


if __name__ == "__main__":
    unittest.main()
