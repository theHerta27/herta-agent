"""Project-scoped CLI ownership of the existing SQLite store and StoredTurn."""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from herta_agent.runtime.messages import Message
from herta_agent.runtime.session import Session
from herta_agent.storage.models import RunConfig, StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.storage.turn import StoredTurn


def history_path(repository, data_dir=None):
    base = data_dir
    if base is None:
        try:
            local = os.environ.get("LOCALAPPDATA")
            base = (
                (Path(local) if local else Path.home() / ".local" / "share") / "HertaAgent" / "cli"
            )
        except RuntimeError:
            raise StoreError(
                "store_path", "无法定位用户数据目录；请显式提供 --data-dir。"
            ) from None
    key = hashlib.sha256(os.path.normcase(str(repository.root)).encode("utf-8")).hexdigest()
    return Path(base) / key / "sessions.sqlite3"


class CLIHistory:
    def __init__(self, path):
        self.store = SQLiteSessionStore(path)
        self._lock = None

    async def open(self):
        # Recovery must never mark another running CLI's tools as interrupted.
        path = self.store.path.with_suffix(".lock")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = path.open("a+b")
            if self._lock.tell() == 0:
                self._lock.write(b"\0")
                self._lock.flush()
            self._lock.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self._lock is not None:
                self._lock.close()
                self._lock = None
            raise StoreError(
                "store_busy", "无法取得项目会话锁；请关闭该项目的另一CLI或检查目录权限。"
            ) from None
        try:
            await self.store.open()
            return await self.store.recover_interrupted()
        except BaseException:
            await self.close()
            raise

    async def close(self):
        try:
            await self.store.close()
        finally:
            if self._lock is not None:
                self._lock.close()  # OS releases the lock on exit, including crashes.
                self._lock = None

    async def session(self, session_id=None):
        if session_id is None:
            record = await self.store.create_session()
            return Session(session_id=record.session_id)
        _, records, _ = await self.store.get_session_snapshot(session_id)
        return Session.restore(session_id, [r.message for r in records])

    async def run(self, agent, session_id, text, *, observer=None):
        session = await self.session(session_id)
        model = getattr(
            getattr(agent.provider, "settings", None), "model", type(agent.provider).__name__
        )
        run_id = uuid4().hex
        try:
            admission = await self.store.admit_run(
                session_id,
                run_id,
                Message(role="user", content=text),
                RunConfig(model=model, settings=agent.settings),
            )
            await self.store.start_run(run_id)
            return await agent.run(
                session,
                text,
                turn_io=StoredTurn(session, self.store, admission),
                observer=observer,
            )
        finally:
            # Admission may commit before cancellation reaches its awaiter.
            cleanup = asyncio.create_task(self._close_run(run_id))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()

    async def _close_run(self, run_id):
        try:
            run = await self.store.get_run(run_id)
        except StoreError as error:
            if error.code == "store_not_found":
                return
            raise
        if run.status in ("created", "running"):
            await self.store.finish_run(
                run_id,
                "cancelled",
                steps=run.steps,
                error="CLI轮次中断，结果未知；未重试。",
            )
