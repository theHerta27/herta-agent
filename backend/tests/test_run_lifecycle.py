import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from test_run_admission import GateProvider

from herta_agent.config import RunSettings
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.runs import RunManager
from herta_agent.storage.models import StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.tools.echo import EchoParameters, echo_registry
from herta_agent.tools.registry import ToolSpec


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteSessionStore(Path(self.temp.name) / "lifecycle.sqlite3")
        await self.store.open()
        self.addAsyncCleanup(self.store.close)
        self.sid = (await self.store.create_session()).session_id
        self.provider = GateProvider()
        self.manager = RunManager(self.store, Agent(self.provider))

    async def test_cancel_running_repeat_and_then_reuse(self):
        handle = await self.manager.submit(self.sid, "go")
        await asyncio.wait_for(self.provider.entered.get(), 2)
        result = await self.manager.cancel(handle.run_id, "user")
        self.assertTrue(result.accepted)
        await self.manager.cancel(handle.run_id, "user")
        await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await self.manager.get(handle.run_id)).run.status, "cancelled")
        self.assertEqual(self.manager.active_count, 0)
        self.provider.release.set()
        again = await self.manager.submit(self.sid, "again")
        await asyncio.wait_for(again.done.wait(), 2)
        result = await self.manager.cancel(again.run_id, "user")
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, "completed")

    async def test_cancel_before_worker_starts_is_owned(self):
        # Defer the worker body while preserving the actual task reference.
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        original = self.manager._execute

        async def delayed(handle):
            entered.set()
            await release.wait()
            await original(handle)

        with patch.object(self.manager, "_execute", delayed):
            handle = await self.manager.submit(self.sid, "go")
            await asyncio.wait_for(entered.wait(), 2)
            await self.manager.cancel(handle.run_id, "user")
            self.assertEqual(self.manager.active_count, 1)
            release.set()
            await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await self.manager.get(handle.run_id)).run.status, "cancelled")
        self.assertEqual(self.provider.requests, [])

    async def test_tool_cleanup_keeps_capacity_and_does_not_repeat_cancel(self):
        started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)

        async def tool(args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        registry = echo_registry()
        registry.register(ToolSpec("wait", "Wait", EchoParameters, tool))

        class Provider:
            async def complete(self, messages, *, tools=()):
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(
                            ToolCall(id="a", name="echo", arguments='{"text":"ok"}'),
                            ToolCall(id="b", name="wait", arguments='{"text":"wait"}'),
                        ),
                    )
                )

        manager = RunManager(self.store, Agent(Provider(), registry=registry))
        handle = await manager.submit(self.sid, "go")
        await asyncio.wait_for(started.wait(), 2)
        await manager.cancel(handle.run_id, "user")
        await asyncio.wait_for(cleaning.wait(), 2)
        await manager.cancel(handle.run_id, "again")
        self.assertEqual(manager.active_count, 1)
        release.set()
        await asyncio.wait_for(handle.done.wait(), 2)
        history = await self.store.load_history(self.sid)
        self.assertIn('"ok": true', history[2].message.content)
        self.assertIn('"cancelled"', history[3].message.content)
        self.assertEqual(manager.active_count, 0)

    async def test_completion_commit_wins_cancel_and_retains_capacity(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        original = self.store.finish_run

        async def gated(*args, **kwargs):
            if args[1] == "completed":
                entered.set()
                await release.wait()
            return await original(*args, **kwargs)

        self.provider.release.set()
        with patch.object(self.store, "finish_run", gated):
            handle = await self.manager.submit(self.sid, "go")
            await asyncio.wait_for(entered.wait(), 2)
            result = await self.manager.cancel(handle.run_id, "user")
            self.assertFalse(result.accepted)
            self.assertEqual(self.manager.active_count, 1)
            release.set()
            await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await self.manager.get(handle.run_id)).run.status, "completed")

    async def test_cancel_during_admission_transaction_never_orphans_run(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store._insert

        def gated(conn, record):
            original(conn, record)
            entered.set()
            if not release.wait(3):
                raise sqlite3.OperationalError("test gate timed out")

        with patch.object(self.store, "_insert", gated):
            caller = asyncio.create_task(self.manager.submit(self.sid, "go"))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                caller.cancel()
                await asyncio.sleep(0)
                self.assertEqual(self.manager.active_count, 1)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(caller, 3)
        self.assertEqual(self.manager.active_count, 0)
        history = await self.store.load_history(self.sid)
        self.assertEqual((await self.store.get_run(history[0].run_id)).status, "cancelled")
        self.assertEqual(self.provider.requests, [])

    async def test_timeout_and_missing_persona_preserve_user(self):
        class Missing:
            def snapshot(self):
                raise ContextError("missing persona")

        for missing in (False, True):
            sid = (await self.store.create_session()).session_id
            agent = Agent(
                GateProvider(),
                RunSettings(request_timeout=0.02),
                context_builder=Missing() if missing else None,
            )
            manager = RunManager(self.store, agent)
            handle = await manager.submit(sid, "go")
            await asyncio.wait_for(handle.done.wait(), 2)
            self.assertEqual((await manager.get(handle.run_id)).run.status, "failed")
            self.assertEqual(len(await self.store.load_history(sid)), 1)

    async def test_shutdown_cancels_runs_closes_store_and_rejects_admission(self):
        handle = await self.manager.submit(self.sid, "go")
        await asyncio.wait_for(self.provider.entered.get(), 2)
        await self.manager.shutdown()
        self.assertTrue(handle.done.is_set())
        self.assertFalse(self.store.writable)
        with self.assertRaises(StoreError):
            await self.manager.submit(self.sid, "late")
        await self.store.open()
        self.assertEqual((await self.store.get_run(handle.run_id)).status, "cancelled")

    async def test_terminal_storage_failure_reports_unpersisted_error(self):
        handle = await self.manager.submit(self.sid, "go")
        await asyncio.wait_for(self.provider.entered.get(), 2)
        conn = sqlite3.connect(self.store.path)
        try:
            conn.execute(
                "CREATE TRIGGER stop_finish BEFORE UPDATE OF status ON runs "
                "WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT, 'fault'); END"
            )
            conn.commit()
        finally:
            conn.close()
        self.provider.release.set()
        await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await self.manager.get(handle.run_id)).run.status, "running")
        events = []
        while not handle.events.empty():
            events.append(handle.events.get_nowait())
        self.assertFalse(events[-1]["payload"]["persisted"])
        self.assertEqual(events[-1]["type"], "service.error")
        self.assertFalse(self.store.writable)

    async def test_worker_creation_failure_closes_admitted_run(self):
        real_create = asyncio.create_task

        def create(coroutine, **kwargs):
            if coroutine.cr_code.co_name == "_execute":
                raise RuntimeError("cannot create worker")
            return real_create(coroutine, **kwargs)

        with patch("herta_agent.service.runs.asyncio.create_task", side_effect=create):
            with self.assertRaises(StoreError):
                await self.manager.submit(self.sid, "go")
        self.assertEqual(self.manager.active_count, 0)
        history = await self.store.load_history(self.sid)
        self.assertEqual((await self.store.get_run(history[0].run_id)).status, "failed")
        self.assertEqual(self.provider.requests, [])

    async def test_cancel_wins_even_if_provider_suppresses_cancellation(self):
        entered = asyncio.Event()

        class Provider:
            async def complete(self, messages, *, tools=()):
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    return ModelReply(message=Message(role="assistant", content="late answer"))

        manager = RunManager(self.store, Agent(Provider()))
        handle = await manager.submit(self.sid, "go")
        await asyncio.wait_for(entered.wait(), 2)
        await manager.cancel(handle.run_id, "user")
        await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await manager.get(handle.run_id)).run.status, "cancelled")
        self.assertEqual(len(await self.store.load_history(self.sid)), 1)

    async def test_notification_failure_after_commit_cannot_change_completed(self):
        self.provider.release.set()
        from herta_agent.service.runs import RunHandle

        original = RunHandle.emit

        async def emit(handle, event):
            if event.type == "llm.completed":
                raise RuntimeError("consumer gone")
            await original(handle, event)

        with patch.object(RunHandle, "emit", emit):
            handle = await self.manager.submit(self.sid, "go")
            await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual((await self.manager.get(handle.run_id)).run.status, "completed")
        self.assertEqual(len(await self.store.load_history(self.sid)), 2)

    async def test_shutdown_timeout_keeps_owner_until_cleanup_finishes(self):
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)

        class Provider:
            async def complete(self, messages, *, tools=()):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release.wait()

        manager = RunManager(self.store, Agent(Provider()))
        handle = await manager.submit(self.sid, "go")
        await asyncio.wait_for(entered.wait(), 2)
        with self.assertRaises(StoreError) as caught:
            await manager.shutdown(grace_seconds=0.02)
        self.assertEqual(caught.exception.code, "shutdown_timeout")
        self.assertTrue(cleaning.is_set())
        self.assertEqual(manager.active_count, 1)
        self.assertTrue(self.store.writable)
        release.set()
        await manager.shutdown()
        self.assertTrue(handle.done.is_set())
        self.assertFalse(self.store.writable)

    async def test_suppressed_cancel_cannot_start_tools_or_next_tool(self):
        await self._suppressed_cancel_case(False)
        await self._suppressed_cancel_case(True)

    async def _suppressed_cancel_case(self, suppress_in_tool):
        entered = asyncio.Event()
        executed = []

        async def wait(args):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "late result"

        async def record(args):
            executed.append("must not execute")
            return "done"

        registry = echo_registry()
        registry.register(ToolSpec("wait", "Wait", EchoParameters, wait))
        registry.register(ToolSpec("record", "Record", EchoParameters, record))
        calls = (ToolCall(id="late", name="record", arguments='{"text":"x"}'),)
        if suppress_in_tool:
            calls = (ToolCall(id="wait", name="wait", arguments='{"text":"x"}'), *calls)

        class Provider:
            count = 0

            async def complete(self, messages, *, tools=()):
                self.count += 1
                if self.count > 1:
                    return ModelReply(message=Message(role="assistant", content="done"))
                if not suppress_in_tool:
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        pass
                return ModelReply(message=Message(role="assistant", tool_calls=calls))

        sid = (await self.store.create_session()).session_id
        manager = RunManager(self.store, Agent(Provider(), registry=registry))
        handle = await manager.submit(sid, "go")
        await asyncio.wait_for(entered.wait(), 2)
        await manager.cancel(handle.run_id, "user")
        await asyncio.wait_for(handle.done.wait(), 2)
        self.assertEqual(executed, [])
        self.assertEqual((await manager.get(handle.run_id)).run.status, "cancelled")
        if not suppress_in_tool:
            self.assertEqual(len(await self.store.load_history(sid)), 1)
