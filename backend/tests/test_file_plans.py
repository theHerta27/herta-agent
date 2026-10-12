import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.workspace.paths import WorkspaceError
from herta_agent.workspace.service import WorkspaceService


class FilePlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_receipt_keeps_owned_identity_after_copy_publish_move_and_restore(self):
        from contextlib import contextmanager

        from herta_agent.workspace.native_io import open_file

        for kind in ("copy", "publish", "move", "restore_move"):
            with self.subTest(kind=kind):
                (self.root / "笔记.md").write_text("原始笔记", encoding="utf-8")
                target = self.root / f"{kind}.md"
                if kind == "publish":
                    plan = self.w.documents._publish(self.id, target.name, b"generated", [])
                elif kind == "restore_move":
                    original = self.propose("move", target="restore-source.md")
                    first = self.jobs.confirm(original["id"], original["digest"], "restore-first")
                    await self.jobs.wait()
                    plan = self.p.preview_undo(first["id"])
                    target = self.root / "笔记.md"
                else:
                    plan = self.propose(kind, target=target.name)
                owned = []

                @contextmanager
                def replacing(path, kind=kind, target=target, owned=owned, **options):
                    with open_file(path, **options) as stream:
                        yield stream
                        if options.get("create") or options.get("delete"):
                            from herta_agent.workspace.file_plans import snapshot

                            owned.append(snapshot(stream))
                    if owned and target.exists() and not (self.root / f"old-{kind}.md").exists():
                        target.rename(self.root / f"old-{kind}.md")
                        target.write_bytes(
                            b"user replacement" if kind == "publish" else "原始笔记".encode()
                        )

                with patch("herta_agent.workspace.file_jobs.open_file", replacing):
                    job = self.jobs.confirm(plan["id"], plan["digest"], f"race-{kind}")
                    await self.jobs.wait()
                receipt = self.jobs.get(job["id"])["receipts"][-1]
                self.assertEqual(receipt["state"], "done")
                self.assertEqual(
                    receipt["data"]["result"], owned[-1], "收据不能接管后来替换的用户文件"
                )
                if kind != "restore_move":
                    self.assertTrue(self.p.preview_undo(job["id"])["conflicts"])
                self.assertTrue(target.exists())
                if kind == "move":
                    (self.root / "笔记.md").write_text("原始笔记", encoding="utf-8")

    async def test_copy_receipt_remains_valid_after_writer_closes(self):
        plan = self.propose()
        job = self.jobs.confirm(plan["id"], plan["digest"], "copy-stable")
        await self.jobs.wait()
        undo = self.p.preview_undo(job["id"])
        self.assertFalse(undo["conflicts"])
        self.jobs.confirm(undo["id"], undo["digest"], "copy-stable-undo")
        await self.jobs.wait()
        self.assertFalse((self.root / "文档").exists())

    async def test_replaced_empty_directory_is_not_deleted_by_undo(self):
        from herta_agent.workspace.native_io import remove_empty_directory

        plan = self.propose("move")
        job = self.jobs.confirm(plan["id"], plan["digest"], "create-for-undo")
        await self.jobs.wait()
        undo = self.p.preview_undo(job["id"])
        target = self.root / "文档"
        displaced = self.root / "original-empty"

        def replacing(path, **options):
            path.rename(displaced)
            path.mkdir()  # Simulates a later user's replacement between check and open.
            return remove_empty_directory(path, **options)

        with patch("herta_agent.workspace.file_jobs.remove_empty_directory", replacing):
            self.jobs.confirm(undo["id"], undo["digest"], "undo-race")
            await self.jobs.wait()
        self.assertTrue(target.is_dir(), "撤销不能删除被用户后来替换的空目录")
        self.assertTrue(displaced.is_dir())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Herta 文件执行 ")
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.root = folder / "files"
        self.root.mkdir()
        (self.root / "笔记.md").write_text("原始笔记", encoding="utf-8")
        (self.root / "photo.txt").write_text("second", encoding="utf-8")
        self.w = WorkspaceService(folder / "workspace.sqlite3")
        self.addCleanup(self.w.close)
        self.id = self.w.grant(str(self.root))["id"]
        self.assertIsNotNone(getattr(self.w, "plans", None), "需要具体预览方案服务")
        self.assertIsNotNone(getattr(self.w, "files", None), "需要拥有式文件执行队列")
        self.p, self.jobs = self.w.plans, self.w.files

    async def asyncTearDown(self):
        await self.w.shutdown()

    def propose(self, kind="copy", source="笔记.md", target="文档/笔记.md"):
        return self.p.propose(self.id, [{"kind": kind, "source": source, "target": target}])

    def test_preview_is_immutable_and_does_not_write_user_directory(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        plan = self.propose()
        self.assertEqual(
            before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        )
        self.assertFalse(plan["conflicts"])
        self.assertTrue(any(op["kind"] == "mkdir" for op in plan["operations"]))
        plan["operations"][0]["target"] = "tampered"
        self.assertNotEqual(self.p.get(plan["id"])["operations"][0]["target"], "tampered")

    def test_native_file_open_and_create_bind_to_directory_handle(self):
        from herta_agent.workspace.directory_guard import directory_guard
        from herta_agent.workspace.native_io import open_file

        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "photo.txt").write_text("outside")
        with directory_guard(self.root.resolve(), writable_children=True) as handle:
            with open_file(outside / "photo.txt", directory_handle=handle) as stream:
                self.assertEqual(stream.read(), b"second")
            with open_file(outside / "new.txt", create=True, directory_handle=handle) as stream:
                stream.write(b"owned")
        self.assertEqual((self.root / "new.txt").read_bytes(), b"owned")
        self.assertFalse((outside / "new.txt").exists())

    async def test_copy_move_receipts_idempotency_and_conditional_undo(self):
        plan = self.propose("move")
        first = self.jobs.confirm(plan["id"], plan["digest"], "first")
        second = self.jobs.confirm(plan["id"], plan["digest"], "second")
        self.assertEqual(first["id"], second["id"])
        await self.jobs.wait()
        job = self.jobs.history(self.id)[0]
        self.assertEqual(job["status"], "completed")
        self.assertFalse((self.root / "笔记.md").exists())
        self.assertEqual((self.root / "文档/笔记.md").read_text("utf-8"), "原始笔记")
        self.assertTrue(all(r["state"] == "done" for r in job["receipts"]))
        undo = self.p.preview_undo(job["id"])
        self.assertFalse(undo["conflicts"])
        self.jobs.confirm(undo["id"], undo["digest"], "undo")
        await self.jobs.wait()
        self.assertEqual((self.root / "笔记.md").read_text("utf-8"), "原始笔记")
        self.assertFalse((self.root / "文档").exists())
        self.assertEqual(
            next(j for j in self.jobs.history(self.id) if j["id"] == job["id"])["status"], "undone"
        )

    async def test_changed_source_is_not_executed_and_existing_target_not_overwritten(self):
        plan = self.propose()
        (self.root / "笔记.md").write_text("后来修改", encoding="utf-8")
        self.jobs.confirm(plan["id"], plan["digest"], "changed")
        await self.jobs.wait()
        self.assertEqual(self.jobs.history(self.id)[0]["status"], "failed")
        self.assertFalse((self.root / "文档").exists())
        (self.root / "taken.md").write_text("keep")
        conflict = self.propose(target="taken.md")
        self.assertTrue(conflict["conflicts"])
        with self.assertRaises(WorkspaceError):
            self.jobs.confirm(conflict["id"], conflict["digest"], "conflict")
        self.assertEqual((self.root / "taken.md").read_text(), "keep")

    def test_digest_revision_protection_and_conflict_checks(self):
        plan = self.propose()
        with self.assertRaises(WorkspaceError):
            self.jobs.confirm(plan["id"], "wrong", "wrong")
        self.w.share(self.id, True)
        with self.assertRaises(WorkspaceError):
            self.jobs.confirm(plan["id"], plan["digest"], "stale")
        for target in ("../out.md", "C:/private", ".env", "bad*.md"):
            with self.subTest(target=target), self.assertRaises(WorkspaceError):
                self.propose(target=target)
        collision = self.p.propose(
            self.id,
            [
                {"kind": "copy", "source": "笔记.md", "target": "Name.md"},
                {"kind": "copy", "source": "photo.txt", "target": "name.md"},
            ],
        )
        self.assertTrue(collision["conflicts"])

    def test_project_scripts_hardlinks_and_revoked_root_are_protected(self):
        project = self.root / "project"
        project.mkdir()
        (project / "package.json").write_text("{}")
        (project / "readme.md").write_text("project")
        with self.assertRaises(WorkspaceError):
            self.propose(source="project/readme.md")
        (self.root / "start.cmd").write_text("echo test")
        with self.assertRaises(WorkspaceError):
            self.propose(source="start.cmd")
        import os

        os.link(self.root / "笔记.md", self.root / "alias.md")
        with self.assertRaises(WorkspaceError):
            self.propose()
        self.w.revoke(self.id)
        with self.assertRaises(WorkspaceError):
            self.propose(source="photo.txt")

    async def test_undo_refuses_edits_and_added_directory_contents(self):
        plan = self.propose()
        job = self.jobs.confirm(plan["id"], plan["digest"], "copy")
        await self.jobs.wait()
        (self.root / "文档/笔记.md").write_text("新工作", encoding="utf-8")
        undo = self.p.preview_undo(job["id"])
        self.assertTrue(undo["conflicts"])
        with self.assertRaises(WorkspaceError):
            self.jobs.confirm(undo["id"], undo["digest"], "undo-edited")
        self.assertEqual((self.root / "文档/笔记.md").read_text("utf-8"), "新工作")

    async def test_extra_directory_contents_conflict_before_undo(self):
        plan = self.propose()
        job = self.jobs.confirm(plan["id"], plan["digest"], "copy-extra")
        await self.jobs.wait()
        (self.root / "文档/keep.txt").write_text("user work")
        self.assertTrue(self.p.preview_undo(job["id"])["conflicts"])
        self.assertTrue((self.root / "文档/笔记.md").exists())

    async def test_control_api_proposes_and_confirms_exact_plan(self):
        from herta_agent.service.app import create_app
        from herta_agent.service.settings import ServiceSettings

        app = create_app(
            ServiceSettings(
                provider="demo",
                db_path=Path(self.temp.name) / "sessions.sqlite3",
                workspace_token="local-control",
            )
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local"
            ) as client:
                headers = {"Authorization": "Bearer local-control"}
                response = await client.post(
                    f"/workspace/roots/{self.id}/plans",
                    headers=headers,
                    json={
                        "operations": [{"kind": "copy", "source": "photo.txt", "target": "new.txt"}]
                    },
                )
                self.assertEqual(response.status_code, 201)
                plan = response.json()
                response = await client.post(
                    f"/workspace/plans/{plan['id']}/confirm",
                    headers=headers,
                    json={"digest": plan["digest"], "request_id": "http"},
                )
                self.assertEqual(response.status_code, 201)
                await app.state.workspace.files.wait()
                self.assertEqual((self.root / "new.txt").read_text(), "second")

    async def test_cancel_copy_removes_only_owned_temporary_output(self):
        from herta_agent.workspace.file_jobs import copy_bytes

        (self.root / "large.bin").write_bytes(b"x" * 8 * 1024 * 1024)
        plan = self.propose(source="large.bin", target="large-copy.bin")
        started = threading.Event()

        def slow_copy(source, destination, check):
            def slow_check():
                started.set()
                threading.Event().wait(0.03)
                check()

            return copy_bytes(source, destination, slow_check)

        with patch("herta_agent.workspace.file_jobs.copy_bytes", slow_copy):
            job = self.jobs.confirm(plan["id"], plan["digest"], "cancel")
            self.assertTrue(await asyncio.to_thread(started.wait, 3))
            self.jobs.cancel(job["id"])
            await self.jobs.wait()
        self.assertEqual(self.jobs.history(self.id)[0]["status"], "cancelled")
        self.assertFalse((self.root / "large-copy.bin").exists())
        self.assertFalse(list(self.root.glob(".herta-*")))
        self.assertEqual((self.root / "large.bin").stat().st_size, 8 * 1024 * 1024)

    def test_restart_preserves_uncertain_intent_without_retry(self):
        plan = self.propose()
        self.w._write(
            "INSERT INTO file_jobs(id,plan_id,root_id,request_id,status,created_at) "
            "VALUES(?,?,?,?,?,?)",
            ("crash", plan["id"], self.id, "crash", "running", "2026-10-12"),
        )
        self.w._write(
            "INSERT INTO file_receipts(job_id,ordinal,state,data) VALUES(?,?,?,?)",
            ("crash", 0, "intent", "{}"),
        )
        other = WorkspaceService(Path(self.temp.name) / "workspace.sqlite3")
        self.addCleanup(other.close)
        job = other.files.history(self.id)[0]
        self.assertEqual(job["status"], "interrupted")
        self.assertEqual(job["receipts"][0]["state"], "intent")
        self.assertFalse((self.root / "文档").exists())

    def test_duplicate_move_source_conflicts_in_preview(self):
        plan = self.p.propose(
            self.id,
            [
                {"kind": "move", "source": "photo.txt", "target": "one.txt"},
                {"kind": "move", "source": "photo.txt", "target": "two.txt"},
            ],
        )
        self.assertTrue(plan["conflicts"])

    async def test_read_and_analysis_cannot_overlap_file_execution(self):
        from herta_agent.workspace.file_jobs import copy_bytes

        plan = self.propose(source="photo.txt", target="copied.txt")
        entered, release = threading.Event(), threading.Event()

        def copying(source, destination, check):
            entered.set()
            release.wait(3)
            return copy_bytes(source, destination, check)

        try:
            with patch("herta_agent.workspace.file_jobs.copy_bytes", copying):
                self.jobs.confirm(plan["id"], plan["digest"], "busy")
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                with self.assertRaises(WorkspaceError):
                    await self.w.io(self.w.list_files, self.id)
                with self.assertRaises(WorkspaceError):
                    self.w.start_analysis(self.id, False)
        finally:
            release.set()
            await self.jobs.wait()
        self.assertEqual(self.jobs.history(self.id)[0]["status"], "completed")

    async def test_same_loop_can_only_propose_and_shared_scope_is_rechecked(self):
        import json

        from herta_agent.runtime.messages import Message, ModelReply, ToolCall
        from herta_agent.service.app import create_app
        from herta_agent.service.settings import ServiceSettings

        outcomes = []
        root_id = self.id

        class ProposalProvider:
            async def complete(self, messages, *, tools=()):
                if messages[-1].role == "tool":
                    outcomes.append(json.loads(messages[-1].content))
                    return ModelReply(message=Message(role="assistant", content="方案已检查"))
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(
                            ToolCall(
                                id="proposal",
                                name="propose_file_plan",
                                arguments=json.dumps(
                                    {
                                        "root_id": root_id,
                                        "operations": [
                                            {
                                                "kind": "copy",
                                                "source": "photo.txt",
                                                "target": "future.txt",
                                            }
                                        ],
                                    }
                                ),
                            ),
                        ),
                    )
                )

        app = create_app(
            ServiceSettings(db_path=Path(self.temp.name) / "sessions.sqlite3"),
            provider=ProposalProvider(),
        )
        async with app.router.lifespan_context(app):
            app.state.workspace.share(self.id, True)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local"
            ) as client:
                session = (await client.post("/sessions", json={})).json()["session_id"]
                response = await client.post(
                    f"/sessions/{session}/runs", json={"text": "提出复制方案"}
                )
                self.assertIn("run.completed", response.text)
                self.assertTrue(outcomes[-1]["ok"])
                self.assertFalse((self.root / "future.txt").exists())
                self.assertNotIn(str(self.root), json.dumps(outcomes[-1]))
                app.state.workspace.share(self.id, False)
                await client.post(f"/sessions/{session}/runs", json={"text": "再次提出"})
                self.assertFalse(outcomes[-1]["ok"])

    async def test_in_place_parent_reparse_change_cannot_redirect_directory_creation(self):
        import ctypes
        import os
        import struct
        from contextlib import contextmanager
        from ctypes import wintypes

        from herta_agent.workspace.directory_guard import directory_guard
        from herta_agent.workspace.native_io import api

        if os.name != "nt":
            self.skipTest("Windows native boundary")
        parent = self.root / "empty-parent"
        parent.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        plan = self.p.propose(self.id, [{"kind": "mkdir", "target": "empty-parent/new-directory"}])
        changed = []

        @contextmanager
        def changing(path, **options):
            with directory_guard(path, **options) as guarded:
                if path == parent.resolve() and options.get("writable_children") and not changed:
                    target = str(outside.resolve())
                    substitute = ("\\??\\" + target).encode("utf-16-le")
                    printed = target.encode("utf-16-le")
                    data = (
                        struct.pack(
                            "<LHHHHHH",
                            0xA0000003,
                            8 + len(substitute) + len(printed) + 4,
                            0,
                            0,
                            len(substitute),
                            len(substitute) + 2,
                            len(printed),
                        )
                        + substitute
                        + b"\0\0"
                        + printed
                        + b"\0\0"
                    )
                    kernel = api()
                    kernel.DeviceIoControl.argtypes = [
                        wintypes.HANDLE,
                        wintypes.DWORD,
                        wintypes.LPVOID,
                        wintypes.DWORD,
                        wintypes.LPVOID,
                        wintypes.DWORD,
                        ctypes.POINTER(wintypes.DWORD),
                        wintypes.LPVOID,
                    ]
                    handle = kernel.CreateFileW(str(path), 0x40000000, 7, None, 3, 0x02200000, None)
                    if handle != ctypes.c_void_p(-1).value:
                        try:
                            buffer = ctypes.create_string_buffer(data)
                            returned = wintypes.DWORD()
                            if kernel.DeviceIoControl(
                                handle,
                                0x000900A4,
                                buffer,
                                len(data),
                                None,
                                0,
                                ctypes.byref(returned),
                                None,
                            ):
                                changed.append(True)
                        finally:
                            kernel.CloseHandle(handle)
                yield guarded

        with patch("herta_agent.workspace.file_jobs.directory_guard", changing):
            self.jobs.confirm(plan["id"], plan["digest"], "directory-retag")
            await self.jobs.wait()
        self.assertFalse((outside / "new-directory").exists(), "目录动作不得写入授权范围外")
