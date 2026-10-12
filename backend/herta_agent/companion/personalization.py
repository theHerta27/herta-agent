"""User-reviewed personalization. Stored instructions never grant tool authority."""

import json
from datetime import UTC, datetime
from uuid import uuid4


def bounded(value, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError("文本长度或格式无效。")
    value = value.strip()
    if not empty and not value:
        raise ValueError("请输入内容。")
    return value


class Personalization:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            for column, definition in (
                ("source", "TEXT NOT NULL DEFAULT 'user'"),
                ("revision", "INTEGER NOT NULL DEFAULT 1"),
            ):
                if column not in {r[1] for r in db.execute("PRAGMA table_info(memories)")}:
                    db.execute(f"ALTER TABLE memories ADD COLUMN {column} {definition}")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS personal_skills(
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,instructions TEXT NOT NULL,
                    source TEXT NOT NULL,status TEXT NOT NULL,enabled INTEGER NOT NULL,
                    revision INTEGER NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_skill_events(
                    id INTEGER PRIMARY KEY,skill_id TEXT NOT NULL,action TEXT NOT NULL,
                    revision INTEGER NOT NULL,created_at TEXT NOT NULL);
            """)

    @staticmethod
    def skill_row(row):
        return {**dict(row), "source": json.loads(row["source"]), "enabled": bool(row["enabled"])}

    def snapshot(self):
        with self.store.connection() as db:
            return {
                "persona": self.store._get(db, "personal_persona", {"text": "", "revision": 1}),
                "voice": self.store._get(
                    db, "personal_voice", {"provider": "piper", "emotion": "neutral"}
                ),
                "skills": [
                    self.skill_row(r)
                    for r in db.execute(
                        "SELECT * FROM personal_skills ORDER BY created_at DESC LIMIT 100"
                    )
                ],
                "memories": [
                    dict(r)
                    for r in db.execute("SELECT * FROM memories ORDER BY rowid DESC LIMIT 100")
                ],
            }

    def persona(self, text, revision):
        text = bounded(text, 6000, empty=True)
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self.store._get(db, "personal_persona", {"text": "", "revision": 1})
            if old["revision"] != revision:
                raise ValueError("人格已更新，请刷新。")
            result = {"text": text, "revision": revision + 1}
            self.store._put(db, "personal_persona", result)
            return result

    def voice(self, provider, emotion):
        if provider not in {"piper", "the_herta"} or emotion not in {
            "neutral",
            "happy",
            "sad",
            "angry",
            "surprised",
        }:
            raise ValueError("语音选项无效。")
        result = {"provider": provider, "emotion": emotion}
        with self.store.connection() as db:
            self.store._put(db, "personal_voice", result)
        return result

    def memory(self, identifier, revision, action, text=None):
        if action not in {"edit", "approve", "disable", "enable"}:
            raise ValueError("记忆动作无效。")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM memories WHERE id=?", (identifier,)).fetchone()
            if not row or row["revision"] != revision:
                raise ValueError("记忆不存在或已变化，请刷新。")
            status = row["status"]
            value = row["text"]
            if action == "edit":
                value, status = bounded(text, 200), "pending"
            elif action == "approve":
                status = "approved"
            elif action == "disable":
                if status != "approved":
                    raise ValueError("只有已保存的记忆可以停用。")
                status = "disabled"
            else:
                if status != "disabled":
                    raise ValueError("只有已审核停用的记忆可以启用。")
                status = "approved"
            db.execute(
                "UPDATE memories SET text=?,status=?,revision=revision+1 WHERE id=?",
                (value, status, identifier),
            )
            return dict(db.execute("SELECT * FROM memories WHERE id=?", (identifier,)).fetchone())

    def propose_skill(self, title, instructions, *, source=None):
        title, instructions = bounded(title, 100), bounded(instructions, 4000)
        row = {
            "id": uuid4().hex,
            "title": title,
            "instructions": instructions,
            "source": source or {"kind": "manual"},
            "status": "pending",
            "enabled": False,
            "revision": 1,
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM personal_skills").fetchone()[0] >= 100:
                raise ValueError("Skills最多100项，请删除不需要的草案。")
            db.execute(
                "INSERT INTO personal_skills VALUES(?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    title,
                    instructions,
                    json.dumps(row["source"], ensure_ascii=False),
                    "pending",
                    0,
                    1,
                    row["created_at"],
                ),
            )
            return row

    def from_task(self, task_id):
        p = self.store.productivity
        task = next((t for t in p.snapshot()["tasks"] if t["id"] == task_id), None)
        events = p.history(task_id) if task else []
        if not task or not any(e["action"] == "complete" for e in events):
            raise ValueError("请选择有完成记录的任务，不能把未完成任务当作成功经验。")
        return self.propose_skill(
            task["title"],
            "适用任务："
            + task["title"]
            + "\n用户记录的方法：\n"
            + (task["notes"] or "尚未记录方法，请补充步骤与成功条件后审核。")
            + "\n使用前核对当前资料、工具授权与结果；遇到范围变化重新确认。",
            source={
                "kind": "completed_task",
                "task_id": task_id,
                "task_revision": task["revision"],
                "events": events[:20],
            },
        )

    def change_skill(self, identifier, revision, action, *, title=None, instructions=None):
        if action not in {"edit", "approve", "disable", "enable", "delete"}:
            raise ValueError("Skill动作无效。")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM personal_skills WHERE id=?", (identifier,)).fetchone()
            if not row or row["revision"] != revision:
                raise ValueError("Skill不存在或已变化，请刷新。")
            if action == "delete":
                db.execute("DELETE FROM personal_skills WHERE id=?", (identifier,))
                return {"deleted": True}
            label, body, status, enabled = (
                row["title"],
                row["instructions"],
                row["status"],
                row["enabled"],
            )
            if action == "edit":
                label = bounded(title, 100) if title is not None else label
                body = bounded(instructions, 4000) if instructions is not None else body
                status, enabled = "pending", 0
            elif action == "approve":
                status, enabled = "approved", 1
            elif action == "enable":
                if status != "approved":
                    raise ValueError("草案必须先审核。")
                enabled = 1
            else:
                enabled = 0
            db.execute(
                "UPDATE personal_skills SET title=?,instructions=?,status=?,enabled=?,"
                "revision=revision+1 WHERE id=?",
                (label, body, status, enabled, identifier),
            )
            db.execute(
                "INSERT INTO personal_skill_events(skill_id,action,revision,created_at) "
                "VALUES(?,?,?,?)",
                (identifier, action, revision + 1, datetime.now(UTC).isoformat()),
            )
            return self.skill_row(
                db.execute("SELECT * FROM personal_skills WHERE id=?", (identifier,)).fetchone()
            )

    def context_skills(self):
        result, remaining = [], 6000
        for row in self.snapshot()["skills"]:
            if row["status"] == "approved" and row["enabled"]:
                text = row["instructions"]
                if len(text) + len(row["title"]) <= remaining:
                    result.append({"title": row["title"], "instructions": text})
                    remaining -= len(text) + len(row["title"])
                if len(result) >= 8:
                    break
        return result
