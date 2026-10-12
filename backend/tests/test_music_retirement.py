import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import httpx

from herta_agent.companion.store import CompanionStore
from herta_agent.companion.tools import companion_tools
from herta_agent.runtime.messages import ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


def legacy_database(folder):
    audio = folder / "用户原始音频.wav"
    audio.write_bytes(b"RIFF-original-user-file")
    path = folder / "companionship.sqlite3"
    prefs = {
        "nickname": "开拓者",
        "volume": 25,
        "auto_read": True,
        "allow_tools": False,
        "quiet_start": 1,
        "quiet_end": 4,
    }
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE tracks(id TEXT PRIMARY KEY,title TEXT NOT NULL,path TEXT NOT NULL UNIQUE);
            CREATE TABLE reminders(id TEXT PRIMARY KEY,title TEXT NOT NULL,due_at TEXT NOT NULL,
                repeat TEXT NOT NULL,enabled INTEGER NOT NULL);
            CREATE TABLE deliveries(id TEXT PRIMARY KEY,reminder_id TEXT NOT NULL,
                title TEXT NOT NULL,due_at TEXT NOT NULL,created_at TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                notified INTEGER NOT NULL DEFAULT 0,UNIQUE(reminder_id,due_at));
            CREATE TABLE memories(id TEXT PRIMARY KEY,text TEXT NOT NULL,status TEXT NOT NULL);
            INSERT INTO reminders VALUES('old-reminder','旧提醒',
                '2099-01-01T00:00:00+00:00','daily',1);
            INSERT INTO deliveries VALUES('old-delivery','old-reminder','旧到期记录',
                '2026-10-10T00:00:00+00:00','2026-10-10T00:00:00+00:00',0,1);
            INSERT INTO memories VALUES('approved','喜欢先看总结','approved');
            INSERT INTO memories VALUES('pending','学习时希望分步解释','pending');
        """)
        db.execute("INSERT INTO tracks VALUES('old-track','用户原始音频',?)", (str(audio),))
        db.executemany(
            "INSERT INTO settings VALUES(?,?)",
            [
                ("preferences", json.dumps(prefs)),
                (
                    "playback",
                    json.dumps(
                        {
                            "revision": 7,
                            "track_id": "old-track",
                            "desired": "playing",
                            "actual": "playing",
                            "volume": 25,
                            "error": "",
                        }
                    ),
                ),
                ("unrelated", '{"keep":true}'),
            ],
        )
    return path, audio


class LegacyDataTests(unittest.TestCase):
    def test_old_records_are_inert_and_other_data_and_original_file_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            path, audio = legacy_database(Path(folder))
            with closing(sqlite3.connect(path)) as db, db:
                old_rows = db.execute("SELECT * FROM settings ORDER BY key").fetchall()
            store = CompanionStore(path)
            snapshot = store.snapshot()
            self.assertEqual(set(snapshot), {"preferences", "reminders", "deliveries", "memories"})
            self.assertEqual(
                snapshot["preferences"],
                {
                    "nickname": "开拓者",
                    "auto_read": True,
                    "allow_tools": False,
                    "quiet_start": 1,
                    "quiet_end": 4,
                },
            )
            self.assertEqual(snapshot["reminders"][0]["id"], "old-reminder")
            self.assertEqual(snapshot["deliveries"][0]["id"], "old-delivery")
            self.assertEqual(len(snapshot["memories"]), 2)
            self.assertEqual(store.context_memories(), ["喜欢先看总结"])
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(
                    db.execute("SELECT * FROM settings ORDER BY key").fetchall(), old_rows
                )
                self.assertEqual(db.execute("SELECT path FROM tracks").fetchone()[0], str(audio))
            self.assertEqual(audio.read_bytes(), b"RIFF-original-user-file")

    def test_saving_preferences_after_upgrade_preserves_other_records_and_reopens(self):
        with tempfile.TemporaryDirectory() as folder:
            path, audio = legacy_database(Path(folder))
            store = CompanionStore(path)
            prefs = store.update_preferences({"nickname": "新称呼", "auto_read": False})
            self.assertNotIn("volume", prefs)
            other = CompanionStore(path)
            self.assertEqual(other.snapshot()["preferences"], prefs)
            self.assertEqual(prefs["quiet_start"], 1)
            self.assertFalse(prefs["allow_tools"])
            self.assertEqual(len(other.snapshot()["memories"]), 2)
            self.assertEqual(len(other.snapshot()["reminders"]), 1)
            self.assertEqual(len(other.snapshot()["deliveries"]), 1)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(
                    json.loads(
                        db.execute("SELECT value FROM settings WHERE key='unrelated'").fetchone()[0]
                    ),
                    {"keep": True},
                )
                self.assertEqual(
                    json.loads(
                        db.execute("SELECT value FROM settings WHERE key='playback'").fetchone()[0]
                    )["revision"],
                    7,
                )
            self.assertTrue(audio.is_file())

    def test_a_fresh_database_does_not_create_retired_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fresh.db"
            store = CompanionStore(path)
            store.update_preferences({"nickname": "保留称呼"})
            with closing(sqlite3.connect(path)) as db, db:
                self.assertIsNone(
                    db.execute("SELECT name FROM sqlite_master WHERE name='tracks'").fetchone()
                )
                self.assertIsNone(
                    db.execute("SELECT value FROM settings WHERE key='playback'").fetchone()
                )


class RetiredBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retired_http_routes_cannot_import_control_report_or_serve_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path, audio = legacy_database(Path(folder))
            app = create_app(
                ServiceSettings(db_path=path.with_name("sessions.db"), provider="demo")
            )
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://local"
                ) as client:
                    for route, body in [
                        ("import", {"paths": [str(audio)]}),
                        ("control", {"action": "pause"}),
                        ("report", {"revision": 7, "actual": "stopped"}),
                    ]:
                        with self.subTest(route=route):
                            self.assertEqual(
                                (
                                    await client.post("/companion/music/" + route, json=body)
                                ).status_code,
                                404,
                            )
                    self.assertEqual(
                        (await client.get("/companion/music/media/old-track")).status_code, 404
                    )
                    prefs = (await client.get("/companion")).json()["preferences"]
                    self.assertEqual(
                        (
                            await client.put("/companion/preferences", json={**prefs, "volume": 80})
                        ).status_code,
                        422,
                    )
                    self.assertEqual(
                        (
                            await client.put(
                                "/companion/preferences", json={**prefs, "nickname": "新称呼"}
                            )
                        ).status_code,
                        200,
                    )
            self.assertEqual(audio.read_bytes(), b"RIFF-original-user-file")

    async def test_retired_tools_are_unknown_even_with_legacy_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = legacy_database(Path(folder))
            specs, policy = companion_tools(CompanionStore(path))
            registry = ToolRegistry()
            for spec in specs:
                registry.register(spec)
            for name in ("search_music", "control_music", "music_status"):
                result = await ToolExecutor(registry, tool_policy=policy).execute(
                    ToolCall(id="retired", name=name, arguments="{}")
                )
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "unknown_tool")
