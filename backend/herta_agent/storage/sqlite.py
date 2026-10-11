"""SQLite facts, recovery and a single connection-owning worker thread."""

import asyncio
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial, wraps
from pathlib import Path
from uuid import uuid4

from herta_agent.runtime.messages import Message
from herta_agent.storage.models import (
    Admission,
    MessageRecord,
    RunConfig,
    RunRecord,
    SessionRecord,
    StoreError,
)
from herta_agent.tools.executor import ToolResult

SCHEMA_VERSION = 2
SCHEMA = (
    """CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        status TEXT NOT NULL CHECK(status IN
            ('created','running','completed','failed','cancelled','interrupted')),
        created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
        steps INTEGER NOT NULL CHECK(steps BETWEEN 0 AND 100),
        context_hash TEXT, config_json TEXT NOT NULL, error TEXT,
        UNIQUE(run_id, session_id))""",
    """CREATE UNIQUE INDEX one_active_run ON runs(session_id)
        WHERE status IN ('created','running')""",
    """CREATE TABLE messages (
        message_id TEXT PRIMARY KEY NOT NULL,
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        run_id TEXT NOT NULL,
        seq INTEGER NOT NULL CHECK(seq > 0),
        step INTEGER NOT NULL CHECK(step BETWEEN 0 AND 100),
        message_json TEXT NOT NULL,
        UNIQUE(session_id, seq),
        FOREIGN KEY(run_id, session_id) REFERENCES runs(run_id, session_id))""",
    "CREATE INDEX run_messages ON messages(run_id, seq)",
    """CREATE TABLE context_diagnostics (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        step INTEGER NOT NULL CHECK(step BETWEEN 1 AND 100),
        kind TEXT NOT NULL CHECK(kind IN ('context','tool')),
        record_key TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(run_id, step, kind, record_key))""",
    """CREATE TABLE context_summaries (
        run_id TEXT NOT NULL REFERENCES runs(run_id), summary_id TEXT NOT NULL,
        source_start INTEGER NOT NULL, source_end INTEGER NOT NULL,
        source_hash TEXT NOT NULL, algorithm TEXT NOT NULL, created_at TEXT NOT NULL,
        text TEXT NOT NULL, PRIMARY KEY(run_id, summary_id))""",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _invalid() -> StoreError:
    return StoreError("store_invalid", "存储输入或消息顺序无效。")


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise _invalid()
    return value


def _integer(value: int, low: int, high: int | None = None) -> int:
    if type(value) is not int or value < low or (high is not None and value > high):
        raise _invalid()
    return value


def _message(value: Message) -> Message:
    if not isinstance(value, Message):
        raise _invalid()
    # Revalidate even model_construct/model_copy objects instead of trusting their type.
    return Message.model_validate_json(value.model_dump_json(), strict=True)


def _check_history(records: tuple[MessageRecord, ...]) -> tuple[set[str], int, bool]:
    """Validate complete batches or a legal unfinished prefix; return last Run state."""
    pending: set[str] = set()
    run_id, last_step, finished = None, 0, False
    seen_runs = set()
    for record in records:
        message = record.message
        if message.role == "user":
            if pending or record.run_id in seen_runs or record.step != 0:
                raise _invalid()
            run_id, last_step, finished = record.run_id, 0, False
            seen_runs.add(run_id)
        elif record.run_id != run_id or finished:
            raise _invalid()
        elif message.role == "assistant":
            if pending or record.step <= last_step:
                raise _invalid()
            last_step = record.step
            pending = {call.id for call in message.tool_calls}
            finished = not pending
        elif message.role == "tool":
            if message.tool_call_id not in pending or record.step != last_step:
                raise _invalid()
            pending.remove(message.tool_call_id)
        else:
            raise _invalid()
    return pending, last_step, finished


async def _settle(future):
    """Cancellation is delivered only after the owned work has actually settled."""
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    try:
        return future.result()  # Always observe the worker's real result/error.
    finally:
        if cancelled:
            raise asyncio.CancelledError


def _on_worker(method):
    @wraps(method)
    async def invoke(self, *args, **kwargs):
        if not self._ready or self._closing is not None:
            raise StoreError("store_state", "数据库未打开或正在关闭。")
        future = asyncio.wrap_future(self._executor.submit(partial(method, self, *args, **kwargs)))
        return await _settle(future)

    return invoke


class SQLiteSessionStore:
    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        self._connection: sqlite3.Connection | None = None
        self._recovery_required = False
        self._writable = False
        self._ready = False
        self._executor: ThreadPoolExecutor | None = None
        self._closing: asyncio.Task | None = None

    @property
    def writable(self) -> bool:
        return (
            self._ready and self._closing is None and self._writable and not self._recovery_required
        )

    async def open(self) -> None:
        if self._executor is not None:
            raise StoreError("store_state", "数据库已经打开或正在切换状态。")
        self._closing = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="herta-sqlite")
        try:
            await _settle(asyncio.wrap_future(self._executor.submit(self._open)))
            self._ready = True
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._executor is None:
            return
        if self._closing is None:
            self._ready = False
            self._closing = asyncio.create_task(self._shutdown())
        await _settle(self._closing)

    async def _shutdown(self):
        executor = self._executor
        try:
            # FIFO: this runs after every operation already accepted by the worker.
            await _settle(asyncio.wrap_future(executor.submit(self._close)))
        finally:
            await asyncio.to_thread(executor.shutdown, wait=True)
            self._executor = None
            self._writable = False
            self._ready = False

    def _open(self) -> None:
        if self._connection is not None:
            raise StoreError("store_state", "数据库已经打开。")
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, isolation_level=None, timeout=1.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if version == 0 and not tables:
                connection.execute("BEGIN IMMEDIATE")
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            elif version == 1 and tables == {"sessions", "runs", "messages"}:
                connection.execute("BEGIN IMMEDIATE")
                for statement in SCHEMA[5:]:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            elif version != SCHEMA_VERSION or tables != {
                "sessions",
                "runs",
                "messages",
                "context_diagnostics",
                "context_summaries",
            }:
                raise StoreError("store_schema", "数据库版本或结构不兼容；未重建数据库。")
            # Check expected columns without repairing an existing database.
            connection.execute("SELECT session_id, created_at, updated_at FROM sessions LIMIT 0")
            connection.execute(
                "SELECT run_id, session_id, status, created_at, started_at, ended_at, "
                "steps, context_hash, config_json, error FROM runs LIMIT 0"
            )
            connection.execute(
                "SELECT message_id, session_id, run_id, seq, step, "
                "message_json FROM messages LIMIT 0"
            )
            self._connection = connection
            self._writable = True
            self._recovery_required = (
                connection.execute(
                    "SELECT 1 FROM runs WHERE status IN ('created','running') LIMIT 1"
                ).fetchone()
                is not None
            )
        except (OSError, sqlite3.Error, StoreError) as error:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            self._connection = None
            self._writable = False
            if isinstance(error, StoreError):
                raise
            raise StoreError("store_open", "无法打开有效的会话数据库。") from None

    def _close(self) -> None:
        try:
            if self._connection is not None:
                self._connection.close()
        except sqlite3.Error:
            raise StoreError("store_close", "会话数据库关闭失败。") from None
        finally:
            self._connection = None
            self._writable = False

    @contextmanager
    def _transaction(self, *, write=False):
        connection = self._connection
        if connection is None:
            raise StoreError("store_state", "数据库尚未打开。")
        if write and not self._writable:
            raise StoreError("store_unwritable", "数据库不可写；需要关闭并重新打开恢复。")
        committing = False
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            committing = True
            connection.commit()
        except BaseException as error:
            # Expected input/uniqueness rejection does not mean storage is broken.
            if isinstance(error, sqlite3.Error) and (
                committing
                or not isinstance(error, sqlite3.IntegrityError)
                or getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_TRIGGER
            ):
                self._writable = False
            try:
                connection.rollback()
            except sqlite3.Error:
                self._writable = False
                raise StoreError("store_operation", "会话数据库回滚失败；存储不可写。") from None
            if isinstance(error, StoreError):
                raise
            if isinstance(error, (sqlite3.Error, ValueError, TypeError)):
                raise StoreError(
                    "store_operation", "会话数据库操作失败；本次事务未提交。"
                ) from None
            raise

    @staticmethod
    def _session(connection, session_id) -> SessionRecord:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id=?", (_identifier(session_id),)
        ).fetchone()
        if row is None:
            raise StoreError("store_not_found", "会话不存在。")
        return SessionRecord(**dict(row))

    @staticmethod
    def _run(connection, run_id) -> RunRecord:
        row = connection.execute(
            "SELECT * FROM runs WHERE run_id=?", (_identifier(run_id),)
        ).fetchone()
        if row is None:
            raise StoreError("store_not_found", "Run不存在。")
        fields = dict(row)
        fields["config"] = RunConfig.model_validate_json(fields.pop("config_json"))
        return RunRecord(**fields)

    @staticmethod
    def _records(connection, session_id) -> tuple[MessageRecord, ...]:
        records = []
        for row in connection.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY seq", (session_id,)
        ):
            fields = dict(row)
            fields["message"] = Message.model_validate_json(fields.pop("message_json"), strict=True)
            records.append(MessageRecord(**fields))
        if [record.seq for record in records] != list(range(1, len(records) + 1)):
            raise _invalid()
        _check_history(tuple(records))
        return tuple(records)

    @staticmethod
    def _insert(connection, record: MessageRecord):
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.message_id,
                record.session_id,
                record.run_id,
                record.seq,
                record.step,
                record.message.model_dump_json(),
            ),
        )
        connection.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?", (_now(), record.session_id)
        )

    @_on_worker
    def create_session(self) -> SessionRecord:
        with self._transaction(write=True) as connection:
            now = _now()
            session = SessionRecord(session_id=uuid4().hex, created_at=now, updated_at=now)
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)", (session.session_id, now, now)
            )
            return session

    @_on_worker
    def get_session(self, session_id: str) -> SessionRecord:
        with self._transaction() as connection:
            return self._session(connection, session_id)

    @_on_worker
    def get_session_snapshot(self, session_id: str):
        """Read history and its terminal state from the same SQLite snapshot."""
        with self._transaction() as connection:
            session = self._session(connection, session_id)
            history = self._records(connection, session_id)
            run = self._run(connection, history[-1].run_id) if history else None
            return session, history, run

    @_on_worker
    def list_sessions(self, after_id=None, limit=50) -> tuple[SessionRecord, ...]:
        with self._transaction() as connection:
            _integer(limit, 1, 100)
            cursor = "" if after_id is None else _identifier(after_id)
            rows = connection.execute(
                "SELECT * FROM sessions WHERE session_id > ? ORDER BY session_id LIMIT ?",
                (cursor, limit),
            )
            return tuple(SessionRecord(**dict(row)) for row in rows)

    @_on_worker
    def load_history(self, session_id: str, before_seq=None) -> tuple[MessageRecord, ...]:
        with self._transaction() as connection:
            self._session(connection, session_id)
            if before_seq is not None:
                _integer(before_seq, 1)
            records = self._records(connection, session_id)
            return tuple(r for r in records if before_seq is None or r.seq < before_seq)

    @_on_worker
    def list_messages(self, session_id: str, after_seq=0, limit=100):
        with self._transaction() as connection:
            self._session(connection, session_id)
            _integer(after_seq, 0)
            _integer(limit, 1, 100)
            return tuple(r for r in self._records(connection, session_id) if r.seq > after_seq)[
                :limit
            ]

    @_on_worker
    def admit_run(self, session_id: str, run_id: str, user: Message, config) -> Admission:
        with self._transaction(write=True) as connection:
            if self._recovery_required:
                raise StoreError("store_recovery", "必须先完成中断恢复才能接纳Run。")
            self._session(connection, session_id)
            _identifier(run_id)
            user = _message(user)
            if user.role != "user":
                raise _invalid()
            if isinstance(config, RunConfig):
                config = RunConfig.model_validate_json(config.model_dump_json())
            else:
                config = RunConfig.model_validate(config)
            history = self._records(connection, session_id)
            record = MessageRecord(
                message_id=uuid4().hex,
                session_id=session_id,
                run_id=run_id,
                seq=len(history) + 1,
                step=0,
                message=user,
            )
            _check_history((*history, record))
            connection.execute(
                "INSERT INTO runs (run_id,session_id,status,created_at,steps,config_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, session_id, "created", _now(), 0, config.model_dump_json()),
            )
            self._insert(connection, record)
            return Admission(run=self._run(connection, run_id), user=record)

    @_on_worker
    def get_run(self, run_id: str) -> RunRecord:
        with self._transaction() as connection:
            return self._run(connection, run_id)

    @_on_worker
    def start_run(self, run_id: str) -> RunRecord:
        with self._transaction(write=True) as connection:
            if self._run(connection, run_id).status != "created":
                raise StoreError("store_transition", "只有created Run可以开始。")
            connection.execute(
                "UPDATE runs SET status='running', started_at=? WHERE run_id=?", (_now(), run_id)
            )
            return self._run(connection, run_id)

    @_on_worker
    def set_context(self, run_id: str, context_hash: str) -> None:
        with self._transaction(write=True) as connection:
            if (
                self._run(connection, run_id).status != "running"
                or not isinstance(context_hash, str)
                or not re.fullmatch("[0-9a-f]{64}", context_hash)
            ):
                raise _invalid()
            connection.execute(
                "UPDATE runs SET context_hash=? WHERE run_id=?", (context_hash, run_id)
            )

    @_on_worker
    def append_message(
        self, run_id: str, message_id: str, step: int, message: Message
    ) -> MessageRecord:
        with self._transaction(write=True) as connection:
            run = self._run(connection, run_id)
            if run.status != "running":
                raise StoreError("store_transition", "只能向running Run追加工具消息。")
            _integer(step, 1, run.config.settings.max_steps)
            message = _message(message)
            if message.role != "tool" and not (message.role == "assistant" and message.tool_calls):
                raise _invalid()  # Text-only answers belong exclusively to finish_run.
            history = self._records(connection, run.session_id)
            record = MessageRecord(
                message_id=message_id,
                session_id=run.session_id,
                run_id=run_id,
                seq=len(history) + 1,
                step=step,
                message=message,
            )
            _check_history((*history, record))
            self._insert(connection, record)
            connection.execute("UPDATE runs SET steps=? WHERE run_id=?", (step, run_id))
            return record

    @_on_worker
    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        steps: int,
        final_message: MessageRecord | None = None,
        error=None,
    ) -> RunRecord:
        """Commit a terminal state and its messages together.

        The caller validates completion protocol and supplies only safe error text.
        """
        with self._transaction(write=True) as connection:
            run = self._run(connection, run_id)
            if status in ("failed", "cancelled"):
                if final_message is not None:
                    raise _invalid()
                return self._abort(connection, run, status, steps, error)
            if status != "completed" or run.status != "running" or error is not None:
                raise StoreError("store_transition", "当前只支持running Run的完整成功提交。")
            _integer(steps, 1, run.config.settings.max_steps)
            if not isinstance(final_message, MessageRecord):
                raise _invalid()
            final = MessageRecord.model_validate_json(final_message.model_dump_json())
            message = _message(final.message)
            history = self._records(connection, run.session_id)
            if (
                final.session_id != run.session_id
                or final.run_id != run_id
                or final.seq != len(history) + 1
                or final.step != steps
                or message.role != "assistant"
                or message.tool_calls
            ):
                raise _invalid()
            _check_history((*history, final))
            self._insert(connection, final)
            connection.execute(
                "UPDATE runs SET status='completed', steps=?, ended_at=? WHERE run_id=?",
                (steps, _now(), run_id),
            )
            return self._run(connection, run_id)

    def _abort(self, connection, run, status, steps, error=None) -> RunRecord:
        if run.status not in ("created", "running"):
            raise StoreError("store_transition", "Run已经结束。")
        _integer(steps, run.steps, run.config.settings.max_steps)
        if error is not None and (not isinstance(error, str) or len(error) > 2000):
            raise _invalid()
        reason = {
            "interrupted": "进程中断，工具结果未知；未重新执行。",
            "cancelled": "本轮已取消，未提交的工具结果未知。",
            "failed": "本轮失败，未提交的工具结果未知。",
        }[status]
        history = self._records(connection, run.session_id)
        if not history or history[-1].run_id != run.run_id:
            raise _invalid()
        pending, step, finished = _check_history(history)
        if finished:
            raise _invalid()
        # Preserve the declaration order; IDs are scoped to the latest batch.
        calls = next((r.message.tool_calls for r in reversed(history) if r.message.tool_calls), ())
        for call in calls:
            if call.id not in pending:
                continue
            record = MessageRecord(
                message_id=uuid4().hex,
                session_id=run.session_id,
                run_id=run.run_id,
                seq=len(history) + 1,
                step=step,
                message=Message(
                    role="tool",
                    tool_call_id=call.id,
                    content=ToolResult.failure(status, reason).to_json(),
                ),
            )
            self._insert(connection, record)
            history = (*history, record)
        _check_history(history)
        connection.execute(
            "UPDATE runs SET status=?, steps=?, ended_at=?, error=? WHERE run_id=?",
            (status, steps, _now(), error or reason, run.run_id),
        )
        return self._run(connection, run.run_id)

    @_on_worker
    def recover_interrupted(self) -> tuple[RunRecord, ...]:
        """Startup-only repair; no model requests or tool handlers are invoked."""
        self._recovery_required = True
        with self._transaction(write=True) as connection:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM runs WHERE status IN ('created','running') ORDER BY run_id"
                )
            ]
            repaired = []
            for run_id in ids:
                run = self._run(connection, run_id)
                repaired.append(self._abort(connection, run, "interrupted", run.steps))
        self._recovery_required = False
        return tuple(repaired)

    @_on_worker
    def record_context(self, run_id, step, package):
        from herta_agent.runtime.context_engine import ContextPackage

        if not isinstance(package, ContextPackage):
            raise _invalid()
        step = _integer(step, 1, 100)
        diagnostic = package.diagnostic(step)
        encoded = json.dumps(diagnostic, ensure_ascii=False, allow_nan=False)
        with self._transaction(write=True) as connection:
            run = self._run(connection, run_id)
            if run.status != "running":
                raise _invalid()
            connection.execute(
                "INSERT INTO context_diagnostics VALUES (?,?,?,?,?,?)",
                (run_id, step, "context", "", encoded, _now()),
            )
            for summary in package.summaries:
                connection.execute(
                    "INSERT OR IGNORE INTO context_summaries VALUES (?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        summary.summary_id,
                        summary.source_start,
                        summary.source_end,
                        summary.source_hash,
                        summary.algorithm,
                        summary.created_at,
                        summary.text,
                    ),
                )

    @_on_worker
    def record_tool_diagnostic(self, run_id, step, call_id, payload):
        step = _integer(step, 1, 100)
        call_id = _identifier(call_id)
        allowed = {"name", "ok", "error_code", "duration_ms", "tool_call_id", "step"}
        if set(payload) - allowed:
            raise _invalid()
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with self._transaction(write=True) as connection:
            run = self._run(connection, run_id)
            if run.status != "running":
                raise _invalid()
            connection.execute(
                "INSERT INTO context_diagnostics VALUES (?,?,?,?,?,?)",
                (run_id, step, "tool", call_id, encoded, _now()),
            )

    @_on_worker
    def get_diagnostics(self, run_id):
        with self._transaction() as connection:
            self._run(connection, run_id)
            rows = connection.execute(
                "SELECT kind, payload_json FROM context_diagnostics "
                "WHERE run_id=? ORDER BY step, created_at, record_key",
                (run_id,),
            ).fetchall()
            return {
                "contexts": [json.loads(r["payload_json"]) for r in rows if r["kind"] == "context"],
                "tools": [json.loads(r["payload_json"]) for r in rows if r["kind"] == "tool"],
            }
