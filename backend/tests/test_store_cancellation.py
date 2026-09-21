"""Deterministic worker ownership, cancellation and SQLite failure contracts."""

import asyncio
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from herta_agent.storage.models import StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "线程 数据.sqlite3"
        self.store = SQLiteSessionStore(self.path)
        self.addAsyncCleanup(self.store.close)

    async def test_cancel_and_close_wait_for_real_commit_on_own_thread(self):
        entered, release, committed = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        armed = False
        threads = []

        class Connection(sqlite3.Connection):
            def commit(conn):
                threads.append(threading.get_ident())
                if armed:
                    entered.set()
                    if not release.wait(3):
                        raise sqlite3.OperationalError("test gate timed out")
                super().commit()
                if armed:
                    committed.set()

            def close(conn):
                threads.append(threading.get_ident())
                super().close()

        real_connect = sqlite3.connect
        with patch(
            "herta_agent.storage.sqlite.sqlite3.connect",
            side_effect=lambda *a, **k: real_connect(*a, **k, factory=Connection),
        ):
            await self.store.open()
        armed = True
        caller = asyncio.create_task(self.store.create_session())
        closer = None
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertNotIn(threading.get_ident(), threads)
            caller.cancel()
            await asyncio.sleep(0)
            caller.cancel()  # Repeated cancellation still cannot abandon the worker.
            closer = asyncio.create_task(self.store.close())
            await asyncio.sleep(0)
            self.assertFalse(caller.done())
            self.assertFalse(closer.done())
            with self.assertRaises(StoreError):
                await self.store.create_session()
        finally:
            release.set()
            await asyncio.gather(caller, *([closer] if closer else []), return_exceptions=True)
        self.assertTrue(caller.cancelled())
        self.assertTrue(committed.is_set())
        self.assertEqual(len(set(threads)), 1)
        await self.store.open()
        self.assertEqual(len(await self.store.list_sessions()), 1)

    async def test_lock_failure_is_bounded_safe_and_disables_writes(self):
        await self.store.open()
        blocker = sqlite3.connect(self.path)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaises(StoreError):
                await asyncio.wait_for(self.store.create_session(), 3)
        finally:
            blocker.rollback()
            blocker.close()
        self.assertFalse(self.store.writable)
        self.assertEqual(await self.store.list_sessions(), ())
        with self.assertRaises(StoreError):
            await self.store.create_session()
        await self.store.close()
        await self.store.open()
        self.assertTrue(self.store.writable)
        await self.store.create_session()

    async def test_commit_failure_rolls_back_and_hides_exception(self):
        secret = uuid4().hex
        armed = False

        class Connection(sqlite3.Connection):
            def commit(conn):
                if armed:
                    raise sqlite3.OperationalError(secret)
                super().commit()

        real_connect = sqlite3.connect
        with patch(
            "herta_agent.storage.sqlite.sqlite3.connect",
            side_effect=lambda *a, **k: real_connect(*a, **k, factory=Connection),
        ):
            await self.store.open()
        armed = True
        with self.assertRaises(StoreError) as caught:
            await self.store.create_session()
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(self.store.writable)
        armed = False
        self.assertEqual(await self.store.list_sessions(), ())

    async def test_open_failure_and_close_are_safe_and_repeatable(self):
        secret = uuid4().hex
        with patch(
            "herta_agent.storage.sqlite.sqlite3.connect",
            side_effect=sqlite3.OperationalError(secret),
        ):
            with self.assertRaises(StoreError) as caught:
                await self.store.open()
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(self.store.writable)
        await self.store.close()
        await self.store.open()
        await asyncio.gather(self.store.close(), self.store.close())
        await self.store.close()
        self.assertFalse(self.store.writable)
        with self.assertRaises(StoreError):
            await self.store.list_sessions()

    async def test_close_failure_is_safe_and_still_shuts_down(self):
        secret = uuid4().hex

        class Connection(sqlite3.Connection):
            def close(conn):
                super().close()
                raise sqlite3.OperationalError(secret)

        real_connect = sqlite3.connect
        with patch(
            "herta_agent.storage.sqlite.sqlite3.connect",
            side_effect=lambda *a, **k: real_connect(*a, **k, factory=Connection),
        ):
            await self.store.open()
        with self.assertRaises(StoreError) as caught:
            await self.store.close()
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(self.store.writable)
        await self.store.close()
        await self.store.open()

    async def test_cancelled_close_waits_until_connection_closed(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()

        class Connection(sqlite3.Connection):
            def close(conn):
                entered.set()
                if not release.wait(3):
                    raise sqlite3.OperationalError("test gate timed out")
                super().close()
                closed.set()

        real_connect = sqlite3.connect
        with patch(
            "herta_agent.storage.sqlite.sqlite3.connect",
            side_effect=lambda *a, **k: real_connect(*a, **k, factory=Connection),
        ):
            await self.store.open()
        closer = asyncio.create_task(self.store.close())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            closer.cancel()
            await asyncio.sleep(0)
            self.assertFalse(closer.done())
        finally:
            release.set()
            await asyncio.gather(closer, return_exceptions=True)
        self.assertTrue(closer.cancelled())
        self.assertTrue(closed.is_set())
