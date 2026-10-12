import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from uuid import uuid4

from herta_agent.companion.store import instant
from herta_agent.workspace.paths import relative_parts

from .models import GoalInput, MaterialInput, TaskInput

ROLES = {
    "default": "保留默认大黑塔表达。",
    "tutor": "作为老师，先确认基础，再分步解释概念与例子，最后给一道检查理解的问题。",
    "interviewer": "作为面试官，一次提出一道问题，依据用户回答追问并给具体改进建议。",
    "recite": "作为背诵陪练，依据用户主动提供的原文和可编辑转写指出遗漏；区分文字差异与语义理解。",
    "review": "作为复盘伙伴，梳理完成、困难、原因与下一步，避免编造未发生的学习记录。",
}
UNSET = object()


class ProductivityStore:
    def __init__(self, daily):
        self.daily = daily
        with daily.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY,title TEXT,notes TEXT,
                    deadline TEXT,status TEXT,revision INTEGER,created_at TEXT);
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,notes TEXT,
                    due_at TEXT,repeat TEXT,remind INTEGER,reminder_id TEXT,goal_id TEXT,
                    status TEXT,revision INTEGER,request_id TEXT UNIQUE,created_at TEXT);
                CREATE TABLE IF NOT EXISTS task_events(id TEXT PRIMARY KEY,task_id TEXT,
                    action TEXT,due_at TEXT,created_at TEXT,data TEXT);
                CREATE TABLE IF NOT EXISTS learning_materials(id TEXT PRIMARY KEY,title TEXT,
                    root_id TEXT,path TEXT,notes TEXT,progress INTEGER,review_count INTEGER,
                    review_at TEXT,revision INTEGER,created_at TEXT);
                CREATE TABLE IF NOT EXISTS learning_events(id TEXT PRIMARY KEY,
                    material_id TEXT,action TEXT,created_at TEXT,data TEXT);
            """)
            if "request_hash" not in {r[1] for r in db.execute("PRAGMA table_info(tasks)")}:
                db.execute("ALTER TABLE tasks ADD COLUMN request_hash TEXT")

    @staticmethod
    def _now(now):
        return (now or datetime.now(UTC)).astimezone(UTC)

    @staticmethod
    def _row(db, table, identifier, revision=None):
        if table not in {"tasks", "goals", "learning_materials"}:
            raise ValueError("无效记录类型。")
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("记录不存在。")
        row = dict(row)
        if table == "tasks":
            row["remind"] = bool(row["remind"])
        if revision is not None and (type(revision) is not int or row["revision"] != revision):
            raise ValueError("记录已变化，请刷新后再操作。")
        return row

    @staticmethod
    def _date(value, now):
        if value is None:
            return None
        date = instant(value)
        if abs(date - now) > timedelta(days=730):
            raise ValueError("任务日期需在前后两年范围内。")
        return date.isoformat()

    def create_goal(self, values):
        request = GoalInput.model_validate(values)
        if not request.title.strip():
            raise ValueError("目标标题不能为空。")
        now = self._now(None)
        deadline = self._date(request.deadline, now)
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM goals").fetchone()[0] >= 100:
                raise ValueError("目标记录已达到100项。")
            identifier = uuid4().hex
            db.execute(
                "INSERT INTO goals VALUES(?,?,?,?, 'active',1,?)",
                (identifier, request.title.strip(), request.notes, deadline, now.isoformat()),
            )
            return self._row(db, "goals", identifier)

    def update_goal(self, identifier, status, revision):
        if status not in {"active", "completed", "cancelled"}:
            raise ValueError("无效目标状态。")
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._row(db, "goals", identifier, revision)
            db.execute(
                "UPDATE goals SET status=?,revision=revision+1 WHERE id=?", (status, identifier)
            )
            return self._row(db, "goals", identifier)

    def create_task(self, values, *, now=None):
        request = TaskInput.model_validate(values)
        now = self._now(now)
        due = self._date(request.due_at, now)
        payload = {
            **request.model_dump(exclude={"request_id"}),
            "title": request.title.strip(),
            "due_at": due,
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if not request.title.strip() or (
            (request.remind or request.repeat != "once") and due is None
        ):
            raise ValueError("任务标题不能为空，提醒和重复任务必须指定含时区日期。")
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if request.request_id:
                row = db.execute(
                    "SELECT * FROM tasks WHERE request_id=?", (request.request_id,)
                ).fetchone()
                if row:
                    if row["request_hash"] != request_hash:
                        raise ValueError("此请求ID已绑定其他任务内容，请刷新后重新创建。")
                    return self._row(db, "tasks", row["id"])
            if db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] >= 500:
                raise ValueError("任务记录已达到500项。")
            if request.goal_id:
                if self._row(db, "goals", request.goal_id)["status"] != "active":
                    raise ValueError("目标已结束，请重新启用或另选目标。")
            reminder = None
            if request.remind:
                if (
                    db.execute("SELECT COUNT(*) FROM reminders WHERE enabled=1").fetchone()[0]
                    >= 200
                ):
                    raise ValueError("启用的提醒已达到200项。")
                reminder = uuid4().hex
                db.execute(
                    "INSERT INTO reminders VALUES(?,?,?,?,1)",
                    (reminder, request.title.strip(), due, request.repeat),
                )
            identifier = uuid4().hex
            db.execute(
                "INSERT INTO tasks(id,title,notes,due_at,repeat,remind,reminder_id,goal_id,"
                "status,revision,request_id,created_at,request_hash) "
                "VALUES(?,?,?,?,?,?,?,?,'open',1,?,?,?)",
                (
                    identifier,
                    request.title.strip(),
                    request.notes,
                    due,
                    request.repeat,
                    int(request.remind),
                    reminder,
                    request.goal_id,
                    request.request_id,
                    now.isoformat(),
                    request_hash,
                ),
            )
            return self._row(db, "tasks", identifier)

    def update_task(
        self, identifier, action, revision, *, due_at=UNSET, title=None, notes=None, now=None
    ):
        now = self._now(now)
        if action not in {"complete", "postpone", "cancel", "reopen", "edit"}:
            raise ValueError("无效任务动作。")
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, "tasks", identifier, revision)
            before_due = row["due_at"]
            if action == "complete":
                if row["status"] != "open":
                    raise ValueError("只有未完成任务可标记完成。")
                row["status"] = "completed"
                if row["repeat"] != "once":
                    interval = timedelta(days=1 if row["repeat"] == "daily" else 7)
                    due = instant(row["due_at"])
                    due += interval * max(1, (now - due) // interval + 1)
                    row.update(status="open", due_at=due.isoformat())
            elif action == "postpone":
                due = self._date(None if due_at is UNSET else due_at, now)
                if not due or instant(due) <= now or row["status"] != "open":
                    raise ValueError("延期需指定未来日期且任务尚未完成。")
                row["due_at"] = due
            elif action == "cancel":
                row["status"] = "cancelled"
            elif action == "reopen":
                row["status"] = "open"
                if due_at is not UNSET:
                    row["due_at"] = self._date(due_at, now)
            else:
                if due_at is not UNSET:
                    row["due_at"] = self._date(due_at, now)
                if title is not None:
                    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                        raise ValueError("标题需为1–200字符。")
                    row["title"] = title.strip()
                if notes is not None:
                    if not isinstance(notes, str) or len(notes) > 2000:
                        raise ValueError("任务备注最多2000字符。")
                    row["notes"] = notes
            if (row["remind"] or row["repeat"] != "once") and not row["due_at"]:
                raise ValueError("关联提醒和重复任务不能清空日期。")
            db.execute(
                "UPDATE tasks SET title=?,notes=?,due_at=?,status=?,revision=revision+1 WHERE id=?",
                (row["title"], row["notes"], row["due_at"], row["status"], identifier),
            )
            if row["reminder_id"]:
                db.execute(
                    "UPDATE reminders SET title=?,due_at=COALESCE(?,due_at),enabled=? WHERE id=?",
                    (
                        row["title"],
                        row["due_at"],
                        int(row["status"] == "open" and bool(row["remind"])),
                        row["reminder_id"],
                    ),
                )
                if action in {"complete", "cancel", "postpone"}:
                    db.execute(
                        "UPDATE deliveries SET acknowledged=1 WHERE reminder_id=?",
                        (row["reminder_id"],),
                    )
            db.execute(
                "INSERT INTO task_events VALUES(?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    identifier,
                    action,
                    before_due,
                    now.isoformat(),
                    json.dumps({"due_at": row["due_at"], "status": row["status"]}),
                ),
            )
            return self._row(db, "tasks", identifier)

    def history(self, identifier):
        with self.daily.connection() as db:
            self._row(db, "tasks", identifier)
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM task_events WHERE task_id=? ORDER BY rowid DESC LIMIT 100",
                    (identifier,),
                )
            ]

    def add_material(self, values, *, now=None):
        request = MaterialInput.model_validate(values)
        if not request.title.strip() or bool(request.root_id) != bool(request.path):
            raise ValueError("资料标题不能为空，目录ID和相对路径必须同时提供。")
        if request.path:
            relative_parts(request.path)
        now = self._now(now)
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM learning_materials").fetchone()[0] >= 200:
                raise ValueError("学习资料记录已达到200项。")
            identifier = uuid4().hex
            db.execute(
                "INSERT INTO learning_materials VALUES(?,?,?,?,?,0,0,?,1,?)",
                (
                    identifier,
                    request.title.strip(),
                    request.root_id,
                    request.path,
                    request.notes,
                    (now + timedelta(days=1)).isoformat(),
                    now.isoformat(),
                ),
            )
            return self._row(db, "learning_materials", identifier)

    def update_material(self, identifier, revision, *, progress, notes, now=None):
        if (
            type(progress) is not int
            or not 0 <= progress <= 100
            or not isinstance(notes, str)
            or len(notes) > 2000
        ):
            raise ValueError("学习进度需为0–100，备注最多2000字符。")
        now = self._now(now)
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._row(db, "learning_materials", identifier, revision)
            db.execute(
                "UPDATE learning_materials SET progress=?,notes=?,review_at=?,"
                "revision=revision+1 WHERE id=?",
                (progress, notes, (now + timedelta(days=1)).isoformat(), identifier),
            )
            db.execute(
                "INSERT INTO learning_events VALUES(?,?,?,?,?)",
                (
                    uuid4().hex,
                    identifier,
                    "progress",
                    now.isoformat(),
                    json.dumps({"progress": progress}),
                ),
            )
            return self._row(db, "learning_materials", identifier)

    def review(self, identifier, revision, *, now=None):
        now = self._now(now)
        with self.daily.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, "learning_materials", identifier, revision)
            count = row["review_count"] + 1
            interval = [1, 3, 7, 14, 30][min(count, 4)]
            db.execute(
                "UPDATE learning_materials SET review_count=?,review_at=?,"
                "revision=revision+1 WHERE id=?",
                (count, (now + timedelta(days=interval)).isoformat(), identifier),
            )
            db.execute(
                "INSERT INTO learning_events VALUES(?,?,?,?,?)",
                (
                    uuid4().hex,
                    identifier,
                    "review",
                    now.isoformat(),
                    json.dumps({"review_count": count}),
                ),
            )
            return self._row(db, "learning_materials", identifier)

    def review_suggestions(self, *, now=None):
        now = self._now(now)
        with self.daily.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM learning_materials WHERE review_at<=? "
                    "ORDER BY review_at LIMIT 20",
                    (now.isoformat(),),
                )
            ]

    def set_role(self, role):
        if role not in ROLES:
            raise ValueError("无效任务角色。")
        with self.daily.connection() as db:
            self.daily._put(db, "task_role", role)
        return {"role": role}

    def snapshot(self):
        with self.daily.connection() as db:
            db.execute("BEGIN")
            tasks = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM tasks ORDER BY "
                    "CASE status WHEN 'open' THEN 0 ELSE 1 END,created_at DESC LIMIT 500"
                )
            ]
            goals = [
                dict(row)
                for row in db.execute("SELECT * FROM goals ORDER BY created_at DESC LIMIT 100")
            ]
            for task in tasks:
                task["remind"] = bool(task["remind"])
            for goal in goals:
                children = [task for task in tasks if task["goal_id"] == goal["id"]]
                goal.update(
                    total_tasks=len(children),
                    completed_tasks=sum(t["status"] == "completed" for t in children),
                )
            return {
                "tasks": tasks,
                "goals": goals,
                "materials": [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM learning_materials ORDER BY created_at DESC LIMIT 200"
                    )
                ],
                "role": self.daily._get(db, "task_role", "default"),
                "timezone": "Asia/Shanghai",
            }

    @staticmethod
    def compare_recitation(expected, transcript):
        if (
            not isinstance(expected, str)
            or not isinstance(transcript, str)
            or not 1 <= len(expected) <= 2000
            or not 1 <= len(transcript) <= 2000
        ):
            raise ValueError("每段原文和转写需为1–2000字符，请分段对照。")

        def normalize(text):
            return re.sub(r"[\W_]+", "", text).lower()

        expected, transcript = normalize(expected), normalize(transcript)
        matcher = SequenceMatcher(None, expected, transcript, autojunk=False)
        missing, added = [], []
        for tag, a, b, c, d in matcher.get_opcodes():
            if tag in {"delete", "replace"}:
                missing.append(expected[a:b])
            if tag in {"insert", "replace"}:
                added.append(transcript[c:d])
        return {
            "missing": missing[:50],
            "added": added[:50],
            "character_match": round(matcher.ratio(), 3),
            "note": "这是忽略标点的文字对照，不是语义评分。先纠正ASR转写，再判断实际遗漏。",
        }
