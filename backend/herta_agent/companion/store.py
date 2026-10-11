"""Small SQLite transactions; no model, shell or audio execution in this store."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from herta_agent.companion.models import MusicInput, Preferences, ReminderInput

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}


def instant(text):
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("提醒时间必须包含时区。")
    return value.astimezone(UTC)


class CompanionStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reminders(
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,due_at TEXT NOT NULL,
                    repeat TEXT NOT NULL,enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries(
                    id TEXT PRIMARY KEY,reminder_id TEXT NOT NULL,title TEXT NOT NULL,
                    due_at TEXT NOT NULL,created_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(reminder_id,due_at));
                CREATE TABLE IF NOT EXISTS memories(
                    id TEXT PRIMARY KEY,text TEXT NOT NULL,status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks(
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,path TEXT NOT NULL UNIQUE);
            """)
            if "notified" not in {row[1] for row in db.execute("PRAGMA table_info(deliveries)")}:
                db.execute("ALTER TABLE deliveries ADD COLUMN notified INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _get(self, db, key, default):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put(self, db, key, value):
        db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def _preferences(self, db):
        return Preferences.model_validate(self._get(db, "preferences", {})).model_dump()

    def _playback(self, db):
        return self._get(
            db,
            "playback",
            {
                "revision": 0,
                "track_id": None,
                "desired": "stopped",
                "actual": "stopped",
                "volume": self._preferences(db)["volume"],
                "error": "",
            },
        )

    def snapshot(self):
        with self.connection() as db:
            db.execute("BEGIN")
            reminders = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM reminders ORDER BY enabled DESC,due_at LIMIT 200"
                )
            ]
            for row in reminders:
                row["enabled"] = bool(row["enabled"])
            return {
                "preferences": self._preferences(db),
                "playback": self._playback(db),
                "reminders": reminders,
                "deliveries": [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM deliveries WHERE acknowledged=0 "
                        "ORDER BY notified,created_at DESC LIMIT 200"
                    )
                ],
                "memories": [
                    dict(row)
                    for row in db.execute("SELECT * FROM memories ORDER BY rowid DESC LIMIT 100")
                ],
                "tracks": [
                    dict(row)
                    for row in db.execute("SELECT id,title FROM tracks ORDER BY rowid LIMIT 1000")
                ],
            }

    def update_preferences(self, values):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prefs = Preferences.model_validate({**self._preferences(db), **values}).model_dump()
            self._put(db, "preferences", prefs)
            if "volume" in values:
                playback = self._playback(db)
                playback.update(volume=prefs["volume"], revision=playback["revision"] + 1)
                self._put(db, "playback", playback)
            return prefs

    def create_reminder(self, title, due_at, repeat="once"):
        request = ReminderInput(title=title.strip(), due_at=due_at, repeat=repeat)
        due = instant(request.due_at)
        row = {
            "id": uuid4().hex,
            "title": request.title,
            "due_at": due.isoformat(),
            "repeat": request.repeat,
            "enabled": True,
        }
        with self.connection() as db:
            if db.execute("SELECT COUNT(*) FROM reminders WHERE enabled=1").fetchone()[0] >= 200:
                raise ValueError("启用的提醒已达到200项，请先取消旧提醒。")
            db.execute("INSERT INTO reminders VALUES(?,?,?,?,?)", tuple(row.values()))
        return row

    def cancel_reminder(self, identifier):
        with self.connection() as db:
            if not db.execute("UPDATE reminders SET enabled=0 WHERE id=?", (identifier,)).rowcount:
                raise ValueError("提醒不存在。")

    def snooze(self, identifier, minutes=10, *, now=None):
        if type(minutes) is not int or not 1 <= minutes <= 10080:
            raise ValueError("稍后提醒分钟数无效。")
        due = (now or datetime.now(UTC)) + timedelta(minutes=minutes)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            reminder = db.execute("SELECT * FROM reminders WHERE id=?", (identifier,)).fetchone()
            if reminder is None:
                raise ValueError("提醒不存在。")
            if reminder["repeat"] == "once":
                db.execute(
                    "UPDATE reminders SET due_at=?,enabled=1 WHERE id=?",
                    (due.isoformat(), identifier),
                )
            else:
                if (
                    db.execute("SELECT COUNT(*) FROM reminders WHERE enabled=1").fetchone()[0]
                    >= 200
                ):
                    raise ValueError("启用的提醒已达到200项，请先取消旧提醒。")
                db.execute(
                    "INSERT INTO reminders VALUES(?,?,?,?,1)",
                    (uuid4().hex, reminder["title"], due.isoformat(), "once"),
                )
            db.execute("UPDATE deliveries SET acknowledged=1 WHERE reminder_id=?", (identifier,))

    def tick(self, now=None):
        now = (now or datetime.now(UTC)).astimezone(UTC)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for reminder in db.execute("SELECT * FROM reminders WHERE enabled=1").fetchall():
                due = instant(reminder["due_at"])
                if due > now:
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO deliveries(id,reminder_id,title,due_at,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (
                        uuid4().hex,
                        reminder["id"],
                        reminder["title"],
                        due.isoformat(),
                        now.isoformat(),
                    ),
                )
                if reminder["repeat"] == "once":
                    db.execute("UPDATE reminders SET enabled=0 WHERE id=?", (reminder["id"],))
                else:
                    interval = timedelta(days=1 if reminder["repeat"] == "daily" else 7)
                    next_due = due + interval * ((now - due) // interval + 1)
                    db.execute(
                        "UPDATE reminders SET due_at=? WHERE id=?",
                        (next_due.isoformat(), reminder["id"]),
                    )

    def acknowledge(self, identifier):
        with self.connection() as db:
            db.execute("UPDATE deliveries SET acknowledged=1 WHERE id=?", (identifier,))

    def mark_notified(self, identifier):
        with self.connection() as db:
            db.execute("UPDATE deliveries SET notified=1 WHERE id=?", (identifier,))

    def propose_memory(self, text):
        text = text.strip()
        if not text or len(text) > 200:
            raise ValueError("记忆内容需为1–200字。")
        with self.connection() as db:
            if db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] >= 100:
                raise ValueError("请先删除不需要的记忆。")
            row = {"id": uuid4().hex, "text": text, "status": "pending"}
            db.execute("INSERT INTO memories VALUES(?,?,?)", tuple(row.values()))
        return row

    def approve_memory(self, identifier):
        with self.connection() as db:
            if not db.execute(
                "UPDATE memories SET status='approved' WHERE id=?", (identifier,)
            ).rowcount:
                raise ValueError("记忆不存在。")

    def delete_memory(self, identifier):
        with self.connection() as db:
            db.execute("DELETE FROM memories WHERE id=?", (identifier,))

    def context_memories(self):
        with self.connection() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT text FROM memories WHERE status='approved' ORDER BY rowid DESC LIMIT 8"
                )
            ]

    def import_tracks(self, paths):
        if not 1 <= len(paths) <= 200:
            raise ValueError("每次导入1–200首音乐。")
        rows = []
        for raw in paths:
            source = Path(raw)
            if not source.is_absolute():
                raise ValueError("音乐路径必须来自文件选择器。")
            path = source.resolve(strict=True)
            if not path.is_file() or path.suffix.lower() not in _AUDIO_EXTENSIONS:
                raise ValueError("请选择本地音频文件。")
            identifier = hashlib.sha256(str(path).encode()).hexdigest()[:32]
            rows.append((identifier, path.stem[:200], str(path)))
        with self.connection() as db:
            existing = db.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            if existing + len(rows) > 1000:
                raise ValueError("音乐库最多1000首。")
            db.executemany("INSERT OR IGNORE INTO tracks VALUES(?,?,?)", rows)
        return [{"id": row[0], "title": row[1]} for row in rows]

    def media_path(self, identifier):
        with self.connection() as db:
            row = db.execute("SELECT path FROM tracks WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("音乐不存在，请重新导入。")
        path = Path(row[0])
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("音乐文件已移动或链接发生变化，请重新导入。")
        return path

    def music_command(self, action, track_id=None, volume=None):
        request = MusicInput(action=action, track_id=track_id, volume=volume)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            playback = self._playback(db)
            ids = [row[0] for row in db.execute("SELECT id FROM tracks ORDER BY rowid")]
            if request.action in ("play", "next", "previous"):
                current = track_id or playback["track_id"] or (ids[0] if ids else None)
                if current not in ids:
                    raise ValueError("音乐库为空或歌曲不存在，请先导入音乐。")
                if request.action in ("next", "previous"):
                    current = ids[(ids.index(current) + (1 if action == "next" else -1)) % len(ids)]
                playback.update(track_id=current, desired="playing")
            elif request.action == "volume":
                if volume is None:
                    raise ValueError("请指定0–100音量。")
                playback["volume"] = volume
                prefs = self._preferences(db)
                prefs["volume"] = volume
                self._put(db, "preferences", prefs)
            else:
                playback["desired"] = "paused" if action == "pause" else "stopped"
            playback.update(revision=playback["revision"] + 1, actual="pending", error="")
            self._put(db, "playback", playback)
            return playback

    def report_playback(self, revision, actual, error=""):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            playback = self._playback(db)
            if playback["revision"] == revision:
                playback.update(actual=actual, error=error[:200])
                self._put(db, "playback", playback)
