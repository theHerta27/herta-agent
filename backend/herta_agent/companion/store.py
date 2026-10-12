"""Small SQLite transactions; no model, shell or audio execution in this store."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from herta_agent.companion.models import Preferences, ReminderInput


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
                CREATE TABLE IF NOT EXISTS reminder_snoozes(
                    reminder_id TEXT PRIMARY KEY,parent_id TEXT NOT NULL,
                    occurrence_due_at TEXT NOT NULL);
            """)
            if "notified" not in {row[1] for row in db.execute("PRAGMA table_info(deliveries)")}:
                db.execute("ALTER TABLE deliveries ADD COLUMN notified INTEGER NOT NULL DEFAULT 0")
        from herta_agent.productivity.store import ProductivityStore

        self.productivity = ProductivityStore(self)
        from herta_agent.companion.personalization import Personalization

        self.personal = Personalization(self)

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
        values = self._get(db, "preferences", {})
        # Compatibility projection only: never reinterpret the retired setting as speech volume.
        if isinstance(values, dict):
            values = {key: value for key, value in values.items() if key != "volume"}
        return Preferences.model_validate(values).model_dump()

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
            }

    def update_preferences(self, values):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prefs = Preferences.model_validate({**self._preferences(db), **values}).model_dump()
            self._put(db, "preferences", prefs)
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
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("UPDATE reminders SET enabled=0 WHERE id=?", (identifier,)).rowcount:
                raise ValueError("提醒不存在。")
            self.clear_snoozes(db, identifier)
            db.execute(
                "UPDATE tasks SET remind=0,revision=revision+1 WHERE reminder_id=?", (identifier,)
            )

    @staticmethod
    def clear_snoozes(db, parent_id):
        # Keep the history; retire only the derived snoozed occurrences.
        children = "SELECT reminder_id FROM reminder_snoozes WHERE parent_id=?"
        db.execute(f"UPDATE reminders SET enabled=0 WHERE id IN ({children})", (parent_id,))
        db.execute(
            f"UPDATE deliveries SET acknowledged=1 WHERE reminder_id IN ({children})",
            (parent_id,),
        )

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
                db.execute(
                    "UPDATE tasks SET due_at=?,revision=revision+1 "
                    "WHERE reminder_id=? AND status='open'",
                    (due.isoformat(), identifier),
                )
            else:
                if (
                    db.execute("SELECT COUNT(*) FROM reminders WHERE enabled=1").fetchone()[0]
                    >= 200
                ):
                    raise ValueError("启用的提醒已达到200项，请先取消旧提醒。")
                child = uuid4().hex
                occurrence = db.execute(
                    "SELECT due_at FROM deliveries WHERE reminder_id=? "
                    "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                    (identifier,),
                ).fetchone()
                db.execute(
                    "INSERT INTO reminders VALUES(?,?,?,?,1)",
                    (child, reminder["title"], due.isoformat(), "once"),
                )
                db.execute(
                    "INSERT INTO reminder_snoozes VALUES(?,?,?)",
                    (child, identifier, occurrence[0] if occurrence else reminder["due_at"]),
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

    def propose_memory(self, text, *, source="user"):
        text = text.strip()
        if not text or len(text) > 200:
            raise ValueError("记忆内容需为1–200字。")
        with self.connection() as db:
            if db.execute("SELECT COUNT(*) FROM memories").fetchone()[0] >= 100:
                raise ValueError("请先删除不需要的记忆。")
            row = {"id": uuid4().hex, "text": text, "status": "pending"}
            db.execute(
                "INSERT INTO memories(id,text,status,source) VALUES(?,?,?,?)",
                (
                    row["id"],
                    text,
                    "pending",
                    source,
                ),
            )
        return row

    def approve_memory(self, identifier):
        with self.connection() as db:
            if not db.execute(
                "UPDATE memories SET status='approved',revision=revision+1 WHERE id=?",
                (identifier,),
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
