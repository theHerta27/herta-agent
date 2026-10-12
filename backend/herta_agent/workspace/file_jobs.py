import asyncio
import hashlib
import json
import os
import threading
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .directory_guard import directory_guard
from .file_plans import snapshot
from .native_io import (
    delete_open_file,
    directory_identity,
    open_file,
    remove_empty_directory,
    rename_open_file,
)
from .paths import WorkspaceError, identity


def copy_bytes(source, destination, check):
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        check()
        destination.write(chunk)
        digest.update(chunk)
    destination.flush()
    os.fsync(destination.fileno())
    check()
    return digest.hexdigest()


class FileJobs:
    def __init__(self, workspace, plans):
        self.w, self.plans = workspace, plans
        self.tasks = {}
        self.errors = {}

    @property
    def active_count(self):
        return sum(not entry[0].done() for entry in self.tasks.values())

    def get(self, job_id):
        rows = self.w._rows("SELECT * FROM file_jobs WHERE id=?", (job_id,))
        if not rows:
            raise WorkspaceError("文件任务不存在。")
        job = rows[0]
        receipts = self.w._rows(
            "SELECT * FROM file_receipts WHERE job_id=? ORDER BY ordinal", (job_id,)
        )
        job["receipts"] = [{**r, "data": json.loads(r["data"])} for r in receipts]
        job["plan"] = self.plans.get(job["plan_id"])
        if job_id in self.errors:
            job.update(status="interrupted", error=self.errors[job_id])
        return job

    def history(self, root_id):
        return [
            self.get(r["id"])
            for r in self.w._rows(
                "SELECT id FROM file_jobs WHERE root_id=? ORDER BY created_at DESC LIMIT 20",
                (root_id,),
            )
        ]

    def confirm(self, plan_id, digest, request_id):
        plan = self.plans.get(plan_id)
        if (
            digest != plan["digest"]
            or not isinstance(request_id, str)
            or not 1 <= len(request_id) <= 64
        ):
            raise WorkspaceError("确认摘要或请求ID无效。")
        existing = self.w._rows(
            "SELECT * FROM file_jobs WHERE plan_id=? OR request_id=?", (plan_id, request_id)
        )
        if existing:
            if existing[0]["plan_id"] != plan_id:
                raise WorkspaceError("请求ID已用于另一方案。")
            return self.get(existing[0]["id"])
        _root, scope = self.plans.scope(plan["root_id"])
        if scope["revision"] != plan["root_revision"] or scope["identity"] != plan["root_identity"]:
            raise WorkspaceError("目录授权已变化，请重新预览。")
        if plan["conflicts"] or datetime.now(UTC) - datetime.fromisoformat(
            plan["created_at"]
        ) > timedelta(minutes=10):
            raise WorkspaceError("方案存在冲突或已超过10分钟，请重新预览。")
        root_id = plan["root_id"]
        if self.w.closing or self.w.active_count:
            raise WorkspaceError("工作台有读取、分析或文件任务，请等待完成后确认。")
        job_id, stop = uuid4().hex, threading.Event()
        self.w._write(
            "INSERT INTO file_jobs(id,plan_id,root_id,request_id,status,created_at) "
            "VALUES(?,?,?,?,'queued',?)",
            (job_id, plan_id, root_id, request_id, datetime.now(UTC).isoformat()),
        )
        task = asyncio.create_task(self._run(job_id, plan, stop))
        self.tasks[root_id] = (task, stop, job_id)
        return self.get(job_id)

    async def _run(self, job_id, plan, stop):
        try:
            await asyncio.to_thread(self._execute, job_id, plan, stop)
        except Exception:
            self.errors[job_id] = "文件动作或收据保存中断，请核查实际文件；未自动重试。"

    def _check(self, plan, stop):
        if stop.is_set():
            raise WorkspaceError("文件任务已停止。")
        root, scope = self.plans.scope(plan["root_id"])
        if scope["revision"] != plan["root_revision"] or scope["identity"] != plan["root_identity"]:
            raise WorkspaceError("目录身份或授权已变化。")
        return root

    def _validate(self, plan, stop):
        root = self._check(plan, stop)
        for path, expected in plan["parents"].items():
            target = root / path if path else root
            if identity(target.lstat()) != expected:
                raise WorkspaceError("父目录已变化，请重新预览。")
            with directory_guard(target):
                self._check(plan, stop)
        for operation in plan["operations"]:
            self._check(plan, stop)
            target = self.plans.safe_path(root, operation["target"])
            if (
                operation["kind"] in {"copy", "move", "mkdir", "restore_move", "publish"}
                and target.exists()
            ):
                raise WorkspaceError(f"目标已经存在：{operation['target']}")
            for proof in operation.get("proofs", []):
                source = self.plans.safe_path(root, proof["path"])
                with (
                    directory_guard(source.parent) as handle,
                    open_file(source, directory_handle=handle) as stream,
                ):
                    if snapshot(stream, lambda: self._check(plan, stop)) != proof["snapshot"]:
                        raise WorkspaceError("生成成果的来源已变化，请重新生成。")
            if operation.get("snapshot"):
                source = self.plans.safe_path(root, operation["source"])
                with directory_guard(source.parent), open_file(source) as stream:
                    if snapshot(stream, lambda: self._check(plan, stop)) != operation["snapshot"]:
                        raise WorkspaceError(f"来源已变化：{operation['source']}")
            if (
                operation["kind"] in {"copy", "publish"}
                and len(str(target.parent).encode("utf-16-le")) // 2 > 227
            ):
                raise WorkspaceError("目标目录过深，无法安全创建临时副本。")
        return root

    def _execute(self, job_id, plan, stop):
        try:
            root = self._validate(plan, stop)  # Complete preflight precedes any directory creation.
            self.w._write("UPDATE file_jobs SET status='running' WHERE id=?", (job_id,))
            created = dict(plan["parents"])
            for ordinal, operation in enumerate(plan["operations"]):
                root = self._check(plan, stop)
                data = {"operation": operation}
                temporary = ".h-" + uuid4().hex[:8]
                if operation["kind"] in {"copy", "publish"}:
                    data["temporary"] = str(
                        (root / operation["target"]).parent.relative_to(root) / temporary
                    ).replace("\\", "/")
                self.w._write(
                    "INSERT INTO file_receipts VALUES(?,?,'intent',?)",
                    (job_id, ordinal, json.dumps(data, ensure_ascii=False)),
                )
                result = self._step(root, plan, operation, stop, created, temporary)
                data["result"] = result
                self.w._write(
                    "UPDATE file_receipts SET state='done',data=? WHERE job_id=? AND ordinal=?",
                    (json.dumps(data, ensure_ascii=False), job_id, ordinal),
                )
                if operation["kind"] == "publish":
                    self.w._write(
                        "UPDATE document_artifacts SET data=NULL,size=0 WHERE id=?",
                        (operation["artifact_id"],),
                    )
                if operation["kind"] == "mkdir":
                    created[operation["target"]] = result["identity"]
            self.w._write("UPDATE file_jobs SET status='completed' WHERE id=?", (job_id,))
            if plan.get("undo_of"):
                self.w._write("UPDATE file_jobs SET status='undone' WHERE id=?", (plan["undo_of"],))
        except Exception as error:
            # An intent without a completed receipt is deliberately uncertain.
            intents = self.w._rows(
                "SELECT ordinal FROM file_receipts WHERE job_id=? AND state='intent'", (job_id,)
            )
            status = "cancelled" if stop.is_set() else "interrupted" if intents else "failed"
            message = (
                str(error)
                if isinstance(error, WorkspaceError)
                else "文件被占用、目录变化或收据保存失败，请核查。"
            )
            self.w._write(
                "UPDATE file_jobs SET status=?,error=? WHERE id=?", (status, message, job_id)
            )

    def _step(self, root, plan, operation, stop, created, temporary):
        kind = operation["kind"]
        target = self.plans.safe_path(root, operation["target"])
        source = (
            self.plans.safe_path(root, operation["source"]) if operation.get("source") else None
        )
        with ExitStack() as guards:
            handles = {}
            for parent in {target.parent, source.parent if source else target.parent}:
                handles[parent] = guards.enter_context(
                    directory_guard(parent, writable_children=True)
                )
                relative = parent.relative_to(root).as_posix() if parent != root else ""
                if relative not in created or identity(parent.lstat()) != created[relative]:
                    raise WorkspaceError("操作父目录已变化。")
            self._check(plan, stop)
            if kind == "mkdir":
                with open_file(
                    target,
                    create=True,
                    directory=True,
                    directory_handle=handles[target.parent],
                ) as directory:
                    return {"identity": directory_identity(directory)}
            if kind == "remove_directory":
                if identity(target.lstat()) != operation["identity"]:
                    raise WorkspaceError("目录被替换，不能撤销。")
                remove_empty_directory(target)
                return {"removed": True}
            if kind == "publish":
                for proof in operation["proofs"]:
                    original = self.plans.safe_path(root, proof["path"])
                    parent_handle = guards.enter_context(
                        directory_guard(original.parent, writable_children=True)
                    )
                    original_stream = guards.enter_context(
                        open_file(original, directory_handle=parent_handle)
                    )
                    if (
                        snapshot(original_stream, lambda: self._check(plan, stop))
                        != proof["snapshot"]
                    ):
                        raise WorkspaceError("来源已变化，请重新生成成果。")
                rows = self.w._rows(
                    "SELECT * FROM document_artifacts WHERE id=? AND root_id=?",
                    (operation["artifact_id"], plan["root_id"]),
                )
                if (
                    not rows
                    or rows[0]["sha256"] != operation["sha256"]
                    or hashlib.sha256(rows[0]["data"]).hexdigest() != operation["sha256"]
                ):
                    raise WorkspaceError("生成成果校验失败。")
                staging = target.parent / temporary
                with open_file(
                    staging, create=True, directory_handle=handles[target.parent]
                ) as outgoing:
                    try:
                        import io

                        digest = copy_bytes(
                            io.BytesIO(rows[0]["data"]), outgoing, lambda: self._check(plan, stop)
                        )
                        if digest != operation["sha256"]:
                            raise WorkspaceError("生成成果发布校验失败。")
                        rename_open_file(outgoing, target, directory_handle=handles[target.parent])
                    except BaseException:
                        delete_open_file(outgoing)
                        raise
                with open_file(target, directory_handle=handles[target.parent]) as stream:
                    return snapshot(stream)
            if kind == "copy":
                staging = target.parent / temporary
                with open_file(source, directory_handle=handles[source.parent]) as incoming:
                    if snapshot(incoming, lambda: self._check(plan, stop)) != operation["snapshot"]:
                        raise WorkspaceError("来源已变化。")
                    with open_file(
                        staging, create=True, directory_handle=handles[target.parent]
                    ) as outgoing:
                        try:
                            digest = copy_bytes(incoming, outgoing, lambda: self._check(plan, stop))
                            if digest != operation["snapshot"]["sha256"]:
                                raise WorkspaceError("副本校验失败。")
                            rename_open_file(
                                outgoing, target, directory_handle=handles[target.parent]
                            )
                        except BaseException:
                            delete_open_file(outgoing)  # Bound to this task's still-open file.
                            raise
            else:
                with open_file(
                    source, delete=True, directory_handle=handles[source.parent]
                ) as stream:
                    if snapshot(stream, lambda: self._check(plan, stop)) != operation["snapshot"]:
                        raise WorkspaceError("文件已被后续修改，不能执行。")
                    if kind == "remove_copy":
                        delete_open_file(stream)
                        return {"removed": True}
                    rename_open_file(stream, target, directory_handle=handles[target.parent])
            with open_file(target, directory_handle=handles[target.parent]) as stream:
                result = snapshot(stream)
                if result["sha256"] != operation["snapshot"]["sha256"]:
                    raise WorkspaceError("完成后文件发生变化，需人工核查。")
            return result

    def cancel(self, job_id):
        for _task, stop, owned_id in self.tasks.values():
            if owned_id == job_id:
                stop.set()

    def cancel_root(self, root_id):
        if root_id in self.tasks:
            self.tasks[root_id][1].set()

    async def wait(self):
        await asyncio.gather(*(asyncio.shield(t) for t, _stop, _id in tuple(self.tasks.values())))

    async def shutdown(self):
        for _task, stop, _id in self.tasks.values():
            stop.set()
        await self.wait()
