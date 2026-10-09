import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx

from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.context import ContextSnapshot
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.storage.models import RunConfig
from herta_agent.storage.sqlite import SCHEMA, SQLiteSessionStore


class HarnessDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_and_summary_persist_and_history_is_unchanged(self):
        from herta_agent.runtime.context_engine import ContextEngine, ContextSettings

        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteSessionStore(Path(temp) / "中文 数据.sqlite3")
            await store.open()
            session = await store.create_session()
            run_id = uuid4().hex
            await store.admit_run(
                session.session_id,
                run_id,
                Message(role="user", content="q"),
                RunConfig(model="fixture"),
            )
            await store.start_run(run_id)
            history = (
                Message(role="user", content="约定：星塔。" + "闲聊" * 500),
                Message(role="assistant", content="记住星塔。"),
                Message(role="user", content="q"),
            )
            package = ContextEngine(
                ContextSettings(window_tokens=1024, output_reserve=128, safety_margin=64)
            ).prepare(history, ContextSnapshot("persona"))
            before = await store.load_history(session.session_id)
            await store.record_context(run_id, 1, package)
            await store.close()
            await store.open()
            try:
                diagnostics = await store.get_diagnostics(run_id)
                self.assertEqual(diagnostics["contexts"][0]["omitted_message_count"], 2)
                self.assertEqual(diagnostics["contexts"][0]["step"], 1)
                self.assertEqual(await store.load_history(session.session_id), before)
                with closing(sqlite3.connect(store.path)) as conn:
                    row = conn.execute("SELECT text, source_hash FROM context_summaries").fetchone()
                self.assertIn("星塔", row[0])
                self.assertEqual(len(row[1]), 64)
                self.assertNotIn("星塔", json.dumps(diagnostics, ensure_ascii=False))
            finally:
                await store.close()

    async def test_old_schema_migrates_without_losing_session(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "v1.sqlite3"
            with closing(sqlite3.connect(db)) as conn:
                for statement in SCHEMA[:5]:
                    conn.execute(statement)
                conn.execute("PRAGMA user_version=1")
                conn.execute("INSERT INTO sessions VALUES ('existing','before','before')")
                conn.commit()
            store = SQLiteSessionStore(db)
            await store.open()
            try:
                self.assertEqual((await store.get_session("existing")).session_id, "existing")
                with closing(sqlite3.connect(db)) as conn:
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            finally:
                await store.close()

    async def test_api_returns_committed_context_after_run_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = ServiceSettings(db_path=Path(temp) / "sessions.db")
            app = create_app(settings, provider=DemoProvider())
            async with app.router.lifespan_context(app):
                session = await app.state.store.create_session()
                handle = await app.state.manager.submit(session.session_id, "你好")
                # Drain events so buffering cannot affect this short run.
                await asyncio.wait_for(handle.done.wait(), 3)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app), base_url="http://local"
                ) as client:
                    response = await client.get(f"/runs/{handle.run_id}/diagnostics")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["contexts"][0]["step"], 1)
                    self.assertNotIn("你好", response.text)
                    self.assertEqual(
                        (await client.get("/runs/missing/diagnostics")).status_code, 404
                    )
            app = create_app(settings, provider=DemoProvider())
            async with app.router.lifespan_context(app):
                value = await app.state.store.get_diagnostics(handle.run_id)
                self.assertEqual(len(value["contexts"]), 1)

    def test_context_env_numeric_validation(self):
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "HERTA_CONTEXT_WINDOW": "8192",
                "HERTA_CONTEXT_OUTPUT_RESERVE": "512",
                "HERTA_CONTEXT_SUMMARY": "false",
            },
            clear=True,
        ):
            settings = ServiceSettings.from_env()
        self.assertEqual(settings.run.context.window_tokens, 8192)
        self.assertEqual(settings.run.context.output_reserve, 512)
        self.assertFalse(settings.run.context.summary_enabled)


class MCPServiceIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_broken_transport_preserves_run_store_and_next_chat(self):
        class Provider:
            calls = 0

            async def complete(self, messages, *, tools=()):
                self.calls += 1
                if self.calls == 1:
                    return ModelReply(
                        message=Message(
                            role="assistant",
                            tool_calls=(
                                ToolCall(id="broken", name="probe_invalid_bytes", arguments="{}"),
                            ),
                        )
                    )
                return ModelReply(message=Message(role="assistant", content="本地聊天继续。"))

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "mcp.json"
            config.write_text(
                json.dumps(
                    {
                        "servers": [
                            {
                                "name": "probe",
                                "command": sys.executable,
                                "args": [str(Path(__file__).with_name("mcp_probe_server.py"))],
                                "allowed_tools": ["probe_invalid_bytes"],
                                "timeout": 2.0,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app = create_app(
                ServiceSettings(db_path=Path(directory) / "sessions.db"), provider=Provider()
            )
            with patch.dict(os.environ, {"HERTA_MCP_CONFIG": str(config)}):
                async with app.router.lifespan_context(app):
                    session = await app.state.store.create_session()
                    first = await app.state.manager.submit(session.session_id, "测试故障")
                    await asyncio.wait_for(first.done.wait(), 10)
                    self.assertEqual(first.terminal.status, "completed")
                    diagnostics = await app.state.store.get_diagnostics(first.run_id)
                    self.assertEqual(diagnostics["tools"][0]["error_code"], "mcp_unavailable")
                    second = await app.state.manager.submit(session.session_id, "继续聊天")
                    await asyncio.wait_for(second.done.wait(), 5)
                    self.assertEqual(second.terminal.status, "completed")
                    self.assertEqual(app.state.manager.active_count, 0)
                    history = await app.state.store.load_history(session.session_id)
                    self.assertEqual(history[-1].message.content, "本地聊天继续。")
                    self.assertEqual(asyncio.current_task().cancelling(), 0)
