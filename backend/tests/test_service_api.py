import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from test_run_admission import GateProvider

from herta_agent.runtime.messages import Message
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.storage.models import RunConfig, StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore


class ServiceAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = ServiceSettings(
            db_path=Path(self.temp.name) / "会话.sqlite3", max_active_runs=1
        )

    async def test_session_snapshot_does_not_mix_old_history_with_new_terminal_state(self):
        provider = GateProvider()
        app = create_app(self.settings, provider=provider)
        async with app.router.lifespan_context(app):
            sid = (await app.state.store.create_session()).session_id
            handle = await app.state.manager.submit(sid, "go")
            await asyncio.wait_for(provider.entered.get(), 2)
            original = app.state.store.load_history

            async def finish_after_read(*args, **kwargs):
                history = await original(*args, **kwargs)
                provider.release.set()
                await asyncio.wait_for(handle.done.wait(), 2)
                return history

            try:
                with patch.object(app.state.store, "load_history", finish_after_read):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app), base_url="http://local"
                    ) as client:
                        snapshot = (await client.get(f"/sessions/{sid}")).json()
                self.assertIn(snapshot["current_run"]["status"], ("running", "completed"))
                expected = 2 if snapshot["current_run"]["status"] == "completed" else 1
                self.assertEqual(len(snapshot["messages"]), expected)
            finally:
                provider.release.set()

    async def test_unconfigured_health_sessions_and_safe_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app(self.settings)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app), base_url="http://local"
                ) as client:
                    health = (await client.get("/health")).json()
                    self.assertFalse(health["chat_available"])
                    self.assertTrue(health["storage_writable"])
                    session = (await client.post("/sessions", json={})).json()
                    sid = session["session_id"]
                    self.assertEqual((await client.get("/sessions")).json()[0], session)
                    self.assertEqual((await client.get(f"/sessions/{sid}")).json()["messages"], [])
                    self.assertEqual(
                        (
                            await client.post(f"/sessions/{sid}/runs", json={"text": "go"})
                        ).status_code,
                        503,
                    )
                    self.assertEqual((await client.get("/sessions/missing")).status_code, 404)
                    self.assertEqual((await client.get("/runs/missing")).status_code, 404)
                    for path in (
                        "/sessions?limit=0",
                        "/sessions?limit=101",
                        f"/sessions/{sid}?after_seq=-1",
                    ):
                        self.assertEqual((await client.get(path)).status_code, 422)
                    secret = uuid4().hex
                    for body in (
                        {"text": " "},
                        {"text": "x" * 10001},
                        {"text": "ok", "api_key": secret},
                        {"messages": []},
                        {"text": 2},
                    ):
                        response = await client.post(f"/sessions/{sid}/runs", json=body)
                        self.assertEqual(response.status_code, 422)
                        self.assertNotIn(secret, response.text)
                    self.assertEqual(
                        (await client.post("/sessions", json={"system": "override"})).status_code,
                        422,
                    )
            self.assertFalse(app.state.store.writable)

    async def test_preflight_conflict_capacity_and_cancel_lookup(self):
        provider = GateProvider()
        app = create_app(self.settings, provider=provider)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://local"
            ) as client:
                first = (await client.post("/sessions")).json()["session_id"]
                second = (await client.post("/sessions")).json()["session_id"]
                handle = await app.state.manager.submit(first, "first")
                await asyncio.wait_for(provider.entered.get(), 2)
                self.assertEqual(
                    (
                        await client.post(f"/sessions/{first}/runs", json={"text": "reject"})
                    ).status_code,
                    409,
                )
                self.assertEqual(
                    (
                        await client.post(f"/sessions/{second}/runs", json={"text": "reject"})
                    ).status_code,
                    429,
                )
                self.assertEqual((await client.get(f"/sessions/{second}")).json()["messages"], [])
                self.assertEqual(
                    (await client.get(f"/runs/{handle.run_id}")).json()["run"]["status"], "running"
                )
                self.assertEqual(
                    (await client.post(f"/runs/{handle.run_id}/cancel")).status_code, 200
                )
                await asyncio.wait_for(handle.done.wait(), 2)
                self.assertEqual(
                    (await client.post(f"/runs/{handle.run_id}/cancel")).json()["status"],
                    "cancelled",
                )

    async def test_startup_recovers_before_accepting_and_shutdown_closes(self):
        store = SQLiteSessionStore(self.settings.db_path)
        await store.open()
        session = await store.create_session()
        await store.admit_run(
            session.session_id,
            "leftover",
            Message(role="user", content="x"),
            RunConfig(model="fake"),
        )
        await store.close()
        app = create_app(self.settings, provider=GateProvider())
        async with app.router.lifespan_context(app):
            self.assertEqual((await app.state.store.get_run("leftover")).status, "interrupted")
        self.assertFalse(app.state.store.writable)

    async def test_startup_failure_closes_store(self):
        app = create_app(self.settings, provider=GateProvider())
        with patch.object(
            SQLiteSessionStore, "recover_interrupted", side_effect=StoreError("test", "safe")
        ):
            with self.assertRaises(StoreError):
                async with app.router.lifespan_context(app):
                    self.fail("startup must fail")
        self.assertFalse(app.state.store.writable)

    async def test_storage_unavailable_is_503(self):
        app = create_app(self.settings, provider=GateProvider())
        async with app.router.lifespan_context(app):
            await app.state.store.close()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://local"
            ) as client:
                self.assertEqual((await client.post("/sessions")).status_code, 503)
                self.assertFalse((await client.get("/health")).json()["storage_writable"])

    def test_settings_paths_and_loopback_single_worker(self):
        from pydantic import ValidationError

        self.assertTrue(ServiceSettings().db_path.is_absolute())
        for kwargs in ({"host": "0.0.0.0"}, {"workers": 2}, {"port": True}):
            with self.assertRaises(ValidationError):
                ServiceSettings(**kwargs)
