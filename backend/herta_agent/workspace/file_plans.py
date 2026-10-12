import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from herta_agent.tools.registry import ToolParameters

from .directory_guard import directory_guard
from .native_io import open_file
from .paths import INTERNAL, WorkspaceError, check_chain, hint, identity, private, relative_parts


class FileOperation(ToolParameters):
    kind: Literal["copy", "move", "mkdir"]
    source: str | None = Field(default=None, max_length=240)
    target: str = Field(min_length=1, max_length=240)


class PlanRequest(ToolParameters):
    root_id: str = Field(min_length=1, max_length=64)
    operations: list[FileOperation] = Field(min_length=1, max_length=100)


def snapshot(stream, check=lambda: None):
    before = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > 256 * 1024 * 1024
    ):
        raise WorkspaceError("仅处理单链接、256 MiB以内的普通文件。")
    digest = hashlib.sha256()
    stream.seek(0)
    while chunk := stream.read(1024 * 1024):
        check()
        digest.update(chunk)
    after = os.fstat(stream.fileno())
    if (identity(before), before.st_size, before.st_mtime_ns, before.st_nlink) != (
        identity(after),
        after.st_size,
        after.st_mtime_ns,
        after.st_nlink,
    ):
        raise WorkspaceError("文件在读取期间变化，请重新预览。")
    stream.seek(0)
    return {
        "identity": identity(after),
        "size": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


class FilePlans:
    def __init__(self, workspace):
        self.w = workspace
        with self.w.lock:
            self.w.db.executescript("""
                CREATE TABLE IF NOT EXISTS file_plans(id TEXT PRIMARY KEY,root_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS file_jobs(id TEXT PRIMARY KEY,
                    plan_id TEXT UNIQUE NOT NULL,
                    root_id TEXT NOT NULL,request_id TEXT UNIQUE NOT NULL,status TEXT NOT NULL,
                    created_at TEXT NOT NULL,error TEXT);
                CREATE TABLE IF NOT EXISTS file_receipts(job_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(job_id,ordinal));
                UPDATE file_jobs SET status='interrupted',error='上次文件操作中断，请核查收据。'
                    WHERE status IN ('queued','running');
            """)

    def scope(self, root_id):
        root = self.w.root(root_id)
        if (
            root == root.parent
            or any(private(p) or p.lower() in INTERNAL for p in root.parts)
            or any(hint(p, p.lstat()) == "project" for p in (root, *root.parents))
        ):
            raise WorkspaceError("修改操作请单独授权普通资料目录，不处理磁盘根或工程目录。")
        record = self.w._rows("SELECT revision,identity FROM roots WHERE id=?", (root_id,))[0]
        return root, record

    def safe_path(self, root, relative):
        parts = relative_parts(relative)
        if not parts or any(private(p) or p.lower() in INTERNAL for p in parts):
            raise WorkspaceError("路径为空或属于受保护资料。")
        if any(
            p.suffix.lower() in {".cmd", ".bat", ".ps1", ".sh", ".dll", ".sys"}
            for p in [Path(relative)]
        ):
            raise WorkspaceError("不规划启动脚本或系统组件。")
        path = root.joinpath(*parts)
        if len(str(path).encode("utf-16-le")) // 2 > 240:
            raise WorkspaceError("完整路径超过240字符，请选择更近的资料目录。")
        for parent in reversed((path.parent, *path.parent.parents)):
            if not parent.is_relative_to(root):
                continue
            if parent.exists():
                check_chain(parent)
                if not parent.is_dir() or hint(parent, parent.lstat()) == "project":
                    raise WorkspaceError("不修改工程内部或非目录路径。")
        if path.exists() or path.is_symlink():
            check_chain(path)
        return path

    def _save(self, root_id, scope, operations, parents, conflicts, *, undo_of=None, db=None):
        payload = {
            "schema_version": 1,
            "root_id": root_id,
            "root_path": str(self.w.root(root_id)),
            "root_revision": scope["revision"],
            "root_identity": scope["identity"],
            "operations": operations,
            "parents": parents,
            "conflicts": conflicts,
            "undo_of": undo_of,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest, plan_id = hashlib.sha256(encoded.encode()).hexdigest(), uuid4().hex
        values = (plan_id, root_id, datetime.now(UTC).isoformat(), digest, encoded)
        if db is None:
            self.w._write("INSERT INTO file_plans VALUES(?,?,?,?,?)", values)
        else:
            db.execute("INSERT INTO file_plans VALUES(?,?,?,?,?)", values)
        return self.get(plan_id)

    def get(self, plan_id, *, private=False):
        rows = self.w._rows("SELECT * FROM file_plans WHERE id=?", (plan_id,))
        if not rows:
            raise WorkspaceError("文件方案不存在。")
        row = rows[0]
        payload = json.loads(row["payload"])
        payload["root_label"] = Path(payload["root_path"]).name
        if not private:
            payload.pop("root_path")
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "digest": row["digest"],
            **payload,
        }

    def history(self, root_id):
        self.w.root(root_id)
        return [
            self.get(r["id"])
            for r in self.w._rows(
                "SELECT id FROM file_plans WHERE root_id=? ORDER BY created_at DESC LIMIT 20",
                (root_id,),
            )
        ]

    def propose(self, root_id, operations, *, cancel=None, shared=False):
        self.w.root(root_id, shared=shared)
        request = PlanRequest(root_id=root_id, operations=operations)
        root, scope = self.scope(root_id)
        parents, normalized, conflicts, destinations, total = {}, [], [], set(), 0
        source_names = {
            op.source.replace("\\", "/").lower() for op in request.operations if op.source
        }
        moved_sources = set()
        new_dirs = set()

        def check():
            self.w.check_cancel(cancel)
            self.w.root(root_id, shared=shared)
            if self.scope(root_id)[1] != scope:
                raise WorkspaceError("授权在预览期间变化。")

        for operation in request.operations:
            self.w.check_cancel(cancel)
            target = self.safe_path(root, operation.target)
            relative = target.relative_to(root).as_posix()
            if relative.lower() in destinations or relative.lower() in source_names:
                conflicts.append(f"目标重复或与来源冲突：{relative}")
            destinations.add(relative.lower())
            if target.exists():
                conflicts.append(f"目标已存在：{relative}")
            for parent in reversed((target.parent, *target.parent.parents)):
                if not parent.is_relative_to(root):
                    continue
                key = parent.relative_to(root).as_posix() if parent != root else ""
                if parent.exists():
                    parents[key] = identity(parent.lstat())
                elif key.lower() not in new_dirs:
                    normalized.append({"kind": "mkdir", "target": key})
                    new_dirs.add(key.lower())
            if operation.kind == "mkdir":
                if operation.source:
                    raise WorkspaceError("创建目录不需要来源。")
                if relative.lower() not in new_dirs:
                    normalized.append({"kind": "mkdir", "target": relative})
                    new_dirs.add(relative.lower())
            else:
                if not operation.source:
                    raise WorkspaceError("复制或移动需要来源文件。")
                source = self.safe_path(root, operation.source)
                source_key = source.relative_to(root).as_posix().lower()
                if operation.kind == "move":
                    if source_key in moved_sources:
                        conflicts.append(f"同一来源不能重复移动：{source_key}")
                    moved_sources.add(source_key)
                with directory_guard(source.parent), open_file(source) as stream:
                    snap = snapshot(stream, check)
                total += snap["size"]
                for parent in (source.parent, *source.parent.parents):
                    if parent.is_relative_to(root):
                        parents[parent.relative_to(root).as_posix() if parent != root else ""] = (
                            identity(parent.lstat())
                        )
                normalized.append(
                    {
                        "kind": operation.kind,
                        "source": source.relative_to(root).as_posix(),
                        "target": relative,
                        "snapshot": snap,
                    }
                )
        if len(normalized) > 100 or total > 1024 * 1024 * 1024:
            raise WorkspaceError("方案超过100动作或1 GiB总量，请拆分任务。")
        self.w.root(root_id, shared=shared)
        if self.scope(root_id)[1] != scope:
            raise WorkspaceError("授权在预览期间变化，请重试。")
        return self._save(root_id, scope, normalized, parents, conflicts)

    def preview_undo(self, job_id):
        job = self.w.files.get(job_id)
        root, scope = self.scope(job["root_id"])
        operations, conflicts, parents = [], [], {}
        if job["status"] == "undone" or job["plan"].get("undo_of"):
            raise WorkspaceError("此任务已经撤销或属于撤销任务。")
        owned = {r["data"]["operation"]["target"] for r in job["receipts"] if r["state"] == "done"}
        for receipt in reversed(job["receipts"]):
            if receipt["state"] != "done":
                continue
            data = receipt["data"]
            operation = data["operation"]
            target = self.safe_path(root, operation["target"])
            try:
                if operation["kind"] == "mkdir":
                    if identity(target.lstat()) != data["result"]["identity"]:
                        raise WorkspaceError("目录已变化。")
                    with directory_guard(target), os.scandir(target) as entries:
                        if any(
                            Path(e.path).relative_to(root).as_posix() not in owned for e in entries
                        ):
                            raise WorkspaceError("目录包含后续新增内容。")
                    action = {
                        "kind": "remove_directory",
                        "target": operation["target"],
                        "identity": data["result"]["identity"],
                    }
                else:
                    with directory_guard(target.parent), open_file(target) as stream:
                        current = snapshot(stream)
                    if current != data["result"]:
                        raise WorkspaceError("目标被后续编辑。")
                    action = {
                        "kind": "restore_move" if operation["kind"] == "move" else "remove_copy",
                        "source": operation["target"],
                        "target": operation.get("source", operation["target"]),
                        "snapshot": current,
                    }
                    if (
                        operation["kind"] == "move"
                        and self.safe_path(root, action["target"]).exists()
                    ):
                        raise WorkspaceError("原位置已被占用。")
                operations.append(action)
                for parent in (target.parent, *target.parent.parents):
                    if parent.is_relative_to(root):
                        parents[parent.relative_to(root).as_posix() if parent != root else ""] = (
                            identity(parent.lstat())
                        )
                if action["kind"] == "restore_move":
                    restored = self.safe_path(root, action["target"])
                    for parent in (restored.parent, *restored.parent.parents):
                        if parent.is_relative_to(root):
                            key = parent.relative_to(root).as_posix() if parent != root else ""
                            expected = job["plan"]["parents"].get(key)
                            if expected and identity(parent.lstat()) != expected:
                                raise WorkspaceError("原父目录已变化。")
                            parents[key] = identity(parent.lstat())
            except (OSError, WorkspaceError):
                conflicts.append(f"不能撤销：{operation['target']}（文件或目录已变化）。")
        if not operations:
            conflicts.append("没有可确认的完成项可撤销。")
        return self._save(job["root_id"], scope, operations, parents, conflicts, undo_of=job_id)
