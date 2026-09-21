import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from herta_agent.runtime.agent import Agent
from herta_agent.runtime.messages import Message, ModelReply
from herta_agent.service.runs import RunCapacityError, RunManager, SessionConflictError
from herta_agent.service.settings import ServiceSettings
from herta_agent.storage.models import StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore


class GateProvider:
    def __init__(self):
        self.entered = asyncio.Queue()
        self.release = asyncio.Event()
        self.requests = []

    async def complete(self, messages, *, tools=()):
        self.requests.append(messages)
        self.entered.put_nowait(True)
        await self.release.wait()
        return ModelReply(message=Message(role="assistant", content="done"))


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteSessionStore(Path(self.temp.name) / "runs.sqlite3")
        await self.store.open()
        self.addAsyncCleanup(self.store.close)
        self.provider = GateProvider()
        self.addCleanup(self.provider.release.set)
        self.manager = RunManager(
            self.store, Agent(self.provider), ServiceSettings(max_active_runs=2)
        )

    async def session(self):
        return (await self.store.create_session()).session_id

    async def test_parallel_sessions_conflict_and_single_user_commit(self):
        first, second = await self.session(), await self.session()
        handles = [
            await self.manager.submit(first, "first"),
            await self.manager.submit(second, "second"),
        ]
        for _ in handles:
            await asyncio.wait_for(self.provider.entered.get(), 2)
        self.assertEqual(self.manager.active_count, 2)
        before = await self.store.load_history(first)
        with self.assertRaises(SessionConflictError) as caught:
            await self.manager.submit(first, "reject")
        self.assertEqual(caught.exception.code, "session_busy")
        self.assertEqual(await self.store.load_history(first), before)
        self.provider.release.set()
        for handle in handles:
            await asyncio.wait_for(handle.done.wait(), 2)
            self.assertEqual((await self.manager.get(handle.run_id)).run.status, "completed")
            self.assertEqual(
                [r.message.role for r in await self.store.load_history(handle.session_id)],
                ["user", "assistant"],
            )
            events = []
            while not handle.events.empty():
                events.append(handle.events.get_nowait())
            self.assertEqual(
                [e["type"] for e in events],
                ["run.started", "llm.started", "llm.completed", "run.completed"],
            )
        self.assertEqual(self.manager.active_count, 0)
        again = await self.manager.submit(first, "again")
        await asyncio.wait_for(again.done.wait(), 2)
        self.assertEqual(len(await self.store.load_history(first)), 4)

    async def test_simultaneous_admission_reserves_capacity_before_await(self):
        manager = RunManager(self.store, Agent(self.provider), ServiceSettings(max_active_runs=1))
        sessions = [await self.session(), await self.session()]
        results = await asyncio.gather(
            *(manager.submit(s, "go") for s in sessions), return_exceptions=True
        )
        rejected = [r for r in results if isinstance(r, RunCapacityError)]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].code, "run_capacity_exceeded")
        handle = next(r for r in results if not isinstance(r, Exception))
        rejected_session = next(s for s in sessions if s != handle.session_id)
        self.assertEqual(await self.store.load_history(rejected_session), ())
        self.provider.release.set()
        await asyncio.wait_for(handle.done.wait(), 2)

    async def test_admit_failure_releases_capacity_without_model_call(self):
        sid = await self.session()
        conn = sqlite3.connect(self.store.path)
        try:
            conn.execute(
                "CREATE TRIGGER stop_admit AFTER INSERT ON messages "
                "BEGIN SELECT RAISE(ABORT, 'fault'); END"
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(StoreError):
            await self.manager.submit(sid, "go")
        self.assertEqual(self.manager.active_count, 0)
        self.assertEqual(self.provider.requests, [])
        self.assertEqual(await self.store.load_history(sid), ())

    async def test_provider_failure_has_persistent_terminal_and_releases(self):
        class Broken:
            async def complete(self, messages, *, tools=()):
                raise RuntimeError("untrusted body")

        manager = RunManager(self.store, Agent(Broken()), ServiceSettings())
        sid = await self.session()
        handle = await manager.submit(sid, "go")
        await asyncio.wait_for(handle.done.wait(), 2)
        run = (await manager.get(handle.run_id)).run
        self.assertEqual(run.status, "failed")
        self.assertNotIn("untrusted body", run.error)
        self.assertEqual(manager.active_count, 0)
        self.assertEqual(len(await self.store.load_history(sid)), 1)

    def test_strict_settings_and_environment(self):
        for value in (True, 0, -1, 33, 1.5, "2"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ServiceSettings(max_active_runs=value)
        with patch.dict(os.environ, {"HERTA_MAX_ACTIVE_RUNS": "3"}):
            self.assertEqual(ServiceSettings.from_env().max_active_runs, 3)
