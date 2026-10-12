import asyncio
import codecs
import itertools
import json
import os
import sqlite3
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .directory_guard import directory_guard
from .paths import (
    INTERNAL,
    TEXT,
    WorkspaceError,
    check_chain,
    grant_path,
    hint,
    identity,
    private,
    relative_parts,
)


class WorkspaceService:
    def __init__(self, db_path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS roots(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,identity TEXT NOT NULL,active INTEGER NOT NULL,
                shared INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,root_id TEXT NOT NULL,
                created_at TEXT NOT NULL,status TEXT NOT NULL,report TEXT,error TEXT);
            UPDATE jobs SET status='interrupted' WHERE status='running';
        """)
        self.db.commit()
        if "revision" not in {row[1] for row in self.db.execute("PRAGMA table_info(roots)")}:
            self.db.execute("ALTER TABLE roots ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
            self.db.commit()
        self.task = None
        self.stop = None
        self.job_id = None
        self.reads = {}
        self.closing = False
        from .file_jobs import FileJobs
        from .file_plans import FilePlans

        self.plans = FilePlans(self)
        self.files = FileJobs(self, self.plans)
        from herta_agent.documents.service import DocumentService

        self.documents = DocumentService(self)

    def close(self):
        self.db.close()

    def _rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _write(self, sql, args):
        with self.lock, self.db:
            self.db.execute(sql, args)

    @staticmethod
    def _public(root):
        return {k: bool(root[k]) if k == "shared" else root[k] for k in ("id", "label", "shared")}

    def roots(self, *, shared=False):
        rows = self._rows(
            "SELECT * FROM roots WHERE active=1"
            + (" AND shared=1" if shared else "")
            + " ORDER BY label"
        )
        return [self._public(r) for r in rows]

    def grant(self, value):
        path = grant_path(value)
        current = self._rows("SELECT * FROM roots WHERE path=?", (str(path),))
        if current and current[0]["active"] and current[0]["identity"] == identity(path.stat()):
            return self._public(current[0])
        if len(self.roots()) >= 50:
            raise WorkspaceError("最多授权 50 个目录，请先撤销不再使用的目录。")
        # A regrant is a new scope; never expose an earlier directory's reports.
        root_id = uuid4().hex
        self._write(
            "INSERT OR REPLACE INTO roots(id,path,label,identity,active,shared) "
            "VALUES(?,?,?,?,1,0)",
            (root_id, str(path), path.name or path.anchor, identity(path.stat())),
        )
        return {"id": root_id, "label": path.name or path.anchor, "shared": False}

    def root(self, root_id, *, shared=False):
        rows = self._rows("SELECT * FROM roots WHERE id=? AND active=1", (root_id,))
        if not rows or (shared and not rows[0]["shared"]):
            raise WorkspaceError("目录未授权或未允许聊天读取。")
        root = rows[0]
        path = Path(root["path"])
        try:
            check_chain(path)
            if identity(path.stat()) != root["identity"] or not path.is_dir():
                raise WorkspaceError("目录已发生变化，请重新选择。")
        except OSError:
            raise WorkspaceError("目录不可用，请重新选择。") from None
        return path

    def resolve(self, root_id, relative="", *, shared=False, text=False):
        root = self.root(root_id, shared=shared)
        parts = relative_parts(relative)
        if text and any(p.lower() in INTERNAL for p in root.parts):
            raise WorkspaceError("依赖、缓存和内部配置目录仅统计大小。")
        if any(private(p) or (text and p.lower() in INTERNAL) for p in parts):
            raise WorkspaceError("此路径受保护，无法读取。")
        path = root.joinpath(*parts)
        try:
            check_chain(path)
            if not path.resolve(strict=True).is_relative_to(root):
                raise WorkspaceError("路径超出授权目录。")
        except OSError:
            raise WorkspaceError("文件不存在或无法访问。") from None
        return path

    def share(self, root_id, enabled):
        self.root(root_id)
        if not isinstance(enabled, bool):
            raise WorkspaceError("共享选项无效。")
        self._write(
            "UPDATE roots SET shared=?,revision=revision+1 WHERE id=?", (int(enabled), root_id)
        )
        return next(r for r in self.roots() if r["id"] == root_id)

    def revoke(self, root_id):
        self._write("UPDATE roots SET active=0,shared=0,revision=revision+1 WHERE id=?", (root_id,))
        self.files.cancel_root(root_id)
        if self.job_id and any(j["id"] == self.job_id for j in self.jobs(root_id, validate=False)):
            self.stop.set()
        for cancel, scope in self.reads.values():
            if scope == root_id:
                cancel.set()

    @staticmethod
    def check_cancel(cancel):
        if cancel is not None and cancel.is_set():
            raise WorkspaceError("文件读取已停止。")

    async def io(self, function, root_id, *args, **kwargs):
        """Own each worker until it exits, even if its caller times out/cancels."""
        if self.closing:
            raise WorkspaceError("文件工作台正在关闭。")
        if self.files.active_count:
            raise WorkspaceError("文件修改正在执行，请稍后读取。")
        cancel = threading.Event()
        task = asyncio.create_task(
            asyncio.to_thread(function, root_id, *args, cancel=cancel, **kwargs)
        )
        self.reads[task] = (cancel, root_id)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel.set()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()  # Observe worker errors before propagating cancellation.
            raise
        finally:
            self.reads.pop(task, None)

    def entry(self, root, path):
        info = path.lstat()
        return {
            "name": path.name,
            "path": path.relative_to(root).as_posix(),
            "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
            "size": info.st_size if stat.S_ISREG(info.st_mode) else 0,
            "hint": hint(path, info),
        }

    def list_files(self, root_id, path="", *, shared=False, cancel=None):
        self.check_cancel(cancel)
        root = self.root(root_id, shared=shared)
        folder = self.resolve(root_id, path, shared=shared)
        try:
            with directory_guard(folder):
                self.resolve(root_id, path, shared=shared)
                with os.scandir(folder) as entries:
                    found = list(itertools.islice(entries, 1001))
                result, skipped = [], False
                for e in found[:1000]:
                    self.check_cancel(cancel)
                    try:
                        result.append(self.entry(root, Path(e.path)))
                    except (OSError, WorkspaceError):
                        skipped = True
            result.sort(key=lambda e: (e["kind"] != "directory", e["name"].lower()))
            self.root(root_id, shared=shared)
            return {"path": path, "entries": result[:200], "truncated": len(found) > 200 or skipped}
        except OSError:
            raise WorkspaceError("目录无法读取。") from None

    def search(self, root_id, query, *, shared=False, cancel=None):
        self.check_cancel(cancel)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 80:
            raise WorkspaceError("请输入 1–80 个字符的文件名。")
        root = self.root(root_id, shared=shared)
        stack, result, visited = [(root, 0)], [], 0
        truncated = False
        while stack and visited < 5000 and len(result) < 100:
            folder, depth = stack.pop()
            self.check_cancel(cancel)
            self.root(root_id, shared=shared)  # Root failures must invalidate the whole operation.
            try:
                with (
                    directory_guard(folder),
                    os.scandir(
                        self.resolve(
                            root_id,
                            folder.relative_to(root).as_posix() if folder != root else "",
                            shared=shared,
                        )
                    ) as entries,
                ):
                    for item in entries:
                        self.check_cancel(cancel)
                        visited += 1
                        if visited > 5000 or len(result) >= 100:
                            truncated = True
                            break
                        try:
                            e = self.entry(root, Path(item.path))
                        except (OSError, WorkspaceError):
                            truncated = True
                            continue
                        if query.lower() in e["name"].lower():
                            result.append(e)
                        if e["kind"] == "directory" and e["hint"] not in {
                            "link",
                            "protected",
                            "cache",
                        }:
                            if depth < 8:
                                stack.append((Path(item.path), depth + 1))
                            else:
                                truncated = True
            except (OSError, WorkspaceError):
                truncated = True
                self.check_cancel(cancel)
        self.root(root_id, shared=shared)
        return {"entries": result, "truncated": truncated or bool(stack)}

    def read_text(self, root_id, path, *, shared=False, cancel=None):
        self.check_cancel(cancel)
        target = self.resolve(root_id, path, shared=shared, text=True)
        if target.suffix.lower() not in TEXT and target.name.lower() not in {"readme", "license"}:
            raise WorkspaceError("当前只预览常见 UTF-8 文本文件。")
        try:
            before = target.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > 1024 * 1024:
                raise WorkspaceError("仅支持 1 MiB 以内的普通文本文件。")
            with directory_guard(target.parent), target.open("rb") as stream:
                if identity(os.fstat(stream.fileno())) != identity(before):
                    raise WorkspaceError("文件已变化，请重试。")
                self.resolve(root_id, path, shared=shared, text=True)
                self.check_cancel(cancel)
                data = stream.read(65537)
            # A preview uses stable line endings across Windows and other platforms.
            decoder = codecs.getincrementaldecoder("utf-8-sig")()
            text = decoder.decode(data[:65536], final=len(data) <= 65536).replace("\r\n", "\n")
            if "\x00" in text:
                raise ValueError
        except (OSError, UnicodeError, ValueError):
            raise WorkspaceError("文本无法读取；要求 UTF-8 编码。") from None
        lines = text.splitlines(keepends=True)
        preview = "".join(lines[:400])[:10000]
        self.check_cancel(cancel)
        self.root(root_id, shared=shared)
        return {
            "path": path,
            "text": preview,
            "start_line": 1,
            "truncated": len(data) > 65536 or preview != text,
        }

    @property
    def active_count(self):
        return (
            self.files.active_count
            + int(self.task is not None and not self.task.done())
            + sum(not t.done() for t in self.reads)
        )

    def jobs(self, root_id, *, validate=True):
        if validate:
            self.root(root_id)
        rows = self._rows(
            "SELECT * FROM jobs WHERE root_id=? ORDER BY created_at DESC LIMIT 20", (root_id,)
        )
        return [{**r, "report": json.loads(r["report"]) if r["report"] else None} for r in rows]

    def start_analysis(self, root_id, duplicates=False):
        self.root(root_id)
        if (
            self.closing
            or self.files.active_count
            or (self.task is not None and not self.task.done())
        ):
            raise WorkspaceError("已有分析正在进行，请先停止或等待完成。")
        job_id = uuid4().hex
        self.stop = threading.Event()
        self.job_id = job_id
        self._write(
            "INSERT INTO jobs(id,root_id,created_at,status) VALUES(?,?,?,'running')",
            (job_id, root_id, datetime.now(UTC).isoformat()),
        )
        self.task = asyncio.create_task(self._analyze(root_id, job_id, duplicates, self.stop))
        return self.jobs(root_id)[0]

    async def _analyze(self, root_id, job_id, duplicates, stop):
        from .analysis import scan

        try:
            report = await asyncio.to_thread(scan, self, root_id, duplicates, stop)
            status = "cancelled" if stop.is_set() else "completed"
            self._write(
                "UPDATE jobs SET status=?,report=? WHERE id=?",
                (status, json.dumps(report, ensure_ascii=False), job_id),
            )
        except Exception:
            self._write(
                "UPDATE jobs SET status=?,error=? WHERE id=?",
                (
                    "cancelled" if stop.is_set() else "failed",
                    "分析中断：目录变化或访问失败。",
                    job_id,
                ),
            )

    def cancel(self, job_id):
        if self.job_id == job_id and self.active_count:
            self.stop.set()

    async def wait_analysis(self):
        if self.task:
            await asyncio.shield(self.task)

    async def shutdown(self):
        self.closing = True
        await self.files.shutdown()
        if self.stop:
            self.stop.set()
        for cancel, _scope in self.reads.values():
            cancel.set()
        await self.wait_analysis()
        if self.reads:
            await asyncio.gather(
                *(asyncio.shield(t) for t in tuple(self.reads)), return_exceptions=True
            )
