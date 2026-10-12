import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.workspace.service import WorkspaceError, WorkspaceService
from herta_agent.workspace.tools import workspace_tools


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = self.folder / "files"
        self.root.mkdir()
        (self.root / "notes.md").write_text("第一行\n第二行", encoding="utf-8")
        (self.root / ".env").write_text("PRIVATE=secret", encoding="utf-8")
        (self.root / "copy.md").write_bytes((self.root / "notes.md").read_bytes())
        project = self.root / "project"
        project.mkdir()
        (project / "package.json").write_text("{}", encoding="utf-8")
        cache = project / "node_modules"
        cache.mkdir()
        (cache / "cache.bin").write_bytes(b"cache" * 10)
        self.service = WorkspaceService(self.folder / "workspace.sqlite3")
        self.addCleanup(self.service.close)
        self.grant = self.service.grant(str(self.root))
        self.id = self.grant["id"]

    def hashes(self):
        return {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def test_listing_search_read_are_scoped_and_readonly(self):
        before = self.hashes()
        listing = self.service.list_files(self.id)
        self.assertGreaterEqual({e["name"] for e in listing["entries"]}, {"notes.md", "project"})
        self.assertEqual(
            next(e for e in listing["entries"] if e["name"] == "project")["hint"], "project"
        )
        self.assertEqual(self.service.search(self.id, "notes")["entries"][0]["path"], "notes.md")
        self.assertEqual(self.service.read_text(self.id, "notes.md")["text"], "第一行\n第二行")
        self.assertEqual(self.hashes(), before)
        self.assertFalse(self.grant["shared"])

    def test_long_chinese_preview_truncates_without_encoding_error(self):
        (self.root / "long.md").write_text("汉" * 30000, encoding="utf-8")
        preview = self.service.read_text(self.id, "long.md")
        self.assertEqual(preview["text"], "汉" * 10000)
        self.assertTrue(preview["truncated"])
        (self.root / "bad.txt").write_bytes(b"bad\xff")
        with self.assertRaises(WorkspaceError):
            self.service.read_text(self.id, "bad.txt")

    def test_unavailable_child_is_skipped_in_search_and_analysis(self):
        from herta_agent.workspace.analysis import scan

        original = self.service.resolve

        def missing_child(root_id, path="", **kwargs):
            if path == "project":
                raise WorkspaceError("子目录不可用")
            return original(root_id, path, **kwargs)

        with patch.object(self.service, "resolve", missing_child):
            result = self.service.search(self.id, "notes")
            self.assertTrue(result["truncated"])
            self.assertEqual(result["entries"][0]["path"], "notes.md")
            report = scan(self.service, self.id, False, threading.Event())
            self.assertTrue(report["partial"])
            self.assertTrue(any(f["path"] == "notes.md" for f in report["files"]))

    def test_windows_directory_replacement_cannot_leak_external_metadata(self):
        if os.name != "nt":
            self.skipTest("Windows directory handle guard")
        from herta_agent.workspace.analysis import scan

        outside = self.folder / "outside"
        outside.mkdir()
        (outside / "external-private.md").write_text("private")
        original = os.scandir
        for index, operation in enumerate(("list", "search", "scan")):
            child = self.root / f"race-{index}"
            child.mkdir()
            child = child.resolve()  # Windows temp paths may use an 8.3 user alias.
            attempted, blocked = [], []

            def racing_scandir(folder, child=child, attempted=attempted, blocked=blocked):
                if Path(folder) == child and not attempted:
                    attempted.append(True)
                    try:
                        child.rename(child.with_name(child.name + "-old"))
                    except OSError:
                        blocked.append(True)
                    else:
                        subprocess.run(
                            ["cmd.exe", "/c", "mklink", "/J", str(child), str(outside)],
                            check=True,
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                return original(folder)

            with self.subTest(operation=operation), patch("os.scandir", racing_scandir):
                if operation == "list":
                    result = self.service.list_files(self.id, child.name)
                elif operation == "search":
                    result = self.service.search(self.id, "external")
                else:
                    result = scan(self.service, self.id, False, threading.Event())
                self.assertNotIn("external-private.md", json.dumps(result))
                self.assertTrue(blocked)

    def test_invalid_and_sensitive_paths_are_refused(self):
        for path in (
            "../outside",
            "C:\\Windows",
            "//server/share",
            "notes.md:stream",
            ".env",
            "project/node_modules/cache.bin",
            "CON",
            "trailing. ",
        ):
            with self.subTest(path=path), self.assertRaises(WorkspaceError):
                self.service.read_text(self.id, path)

    def test_cache_root_does_not_bypass_text_protection(self):
        root = self.service.grant(str(self.root / "project" / "node_modules"))
        (self.root / "project" / "node_modules" / "config.json").write_text("{}")
        with self.assertRaises(WorkspaceError):
            self.service.read_text(root["id"], "config.json")

    def test_system_and_credential_descendants_are_protected(self):
        for name in ("Windows", ".npmrc", "credentials.json"):
            target = self.root / name
            if name == "Windows":
                target.mkdir()
                target = target / "config.json"
            target.write_text("private")
            with self.subTest(name=name), self.assertRaises(WorkspaceError):
                self.service.read_text(self.id, target.relative_to(self.root).as_posix())

    def test_persistence_and_revocation(self):
        other = WorkspaceService(self.folder / "workspace.sqlite3")
        self.addCleanup(other.close)
        self.assertEqual(other.roots()[0]["id"], self.id)
        self.service.revoke(self.id)
        with self.assertRaises(WorkspaceError):
            other.list_files(self.id)
        self.assertEqual(other.roots(), [])

    def test_changed_root_and_links(self):
        outside = self.folder / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        try:
            (self.root / "link.txt").symlink_to(outside)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with self.assertRaises(WorkspaceError):
            self.service.read_text(self.id, "link.txt")
        self.root.rename(self.root.with_name("old"))
        self.root.mkdir()
        with self.assertRaises(WorkspaceError):
            self.service.list_files(self.id)

    def test_network_device_relative_roots(self):
        for root in ("\\\\server\\share", "\\\\?\\C:\\temp", "\\\\.\\PhysicalDrive0", "relative"):
            with self.subTest(root=root), self.assertRaises(WorkspaceError):
                self.service.grant(root)

    async def test_tools_require_fresh_explicit_sharing(self):
        specs = {s.name: s for s in workspace_tools(self.service)}
        tool = specs["read_workspace_text"]
        args = tool.parameters(root_id=self.id, path="notes.md")
        with self.assertRaises(WorkspaceError):
            await tool.handler(args)
        self.service.share(self.id, True)
        self.assertIn("第一行", str(await tool.handler(args)))
        self.service.share(self.id, False)
        with self.assertRaises(WorkspaceError):
            await tool.handler(args)
        self.assertTrue(all(s.permission == "read_only" for s in specs.values()))

    async def test_revocation_during_tool_read_suppresses_late_result(self):
        import asyncio

        self.service.share(self.id, True)
        tool = next(s for s in workspace_tools(self.service) if s.name == "read_workspace_text")
        original = self.service.read_text
        started, release = threading.Event(), threading.Event()

        def slow_read(*args, **kwargs):
            value = original(*args, **kwargs)
            started.set()
            release.wait(5)
            return value

        with patch.object(self.service, "read_text", slow_read):
            task = asyncio.create_task(
                tool.handler(tool.parameters(root_id=self.id, path="notes.md"))
            )
            await asyncio.to_thread(started.wait, 3)
            self.service.share(self.id, False)
            release.set()
            with self.assertRaises(WorkspaceError):
                await task

    async def test_cancelled_tool_thread_remains_owned_until_it_stops(self):
        self.service.share(self.id, True)
        tool = next(s for s in workspace_tools(self.service) if s.name == "read_workspace_text")
        started, release, stopped = threading.Event(), threading.Event(), threading.Event()
        original = self.service.read_text

        def slow_read(*args, cancel=None, **kwargs):
            try:
                result = original(*args, **kwargs)
                started.set()
                while not release.wait(0.02):
                    if cancel and cancel.is_set():
                        break
                return result
            finally:
                stopped.set()

        with patch.object(self.service, "read_text", slow_read):
            task = asyncio.create_task(
                tool.handler(tool.parameters(root_id=self.id, path="notes.md"))
            )
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.assertGreaterEqual(self.service.active_count, 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await self.service.shutdown()
                self.assertTrue(stopped.is_set())
                self.assertEqual(self.service.active_count, 0)
            finally:
                release.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.to_thread(stopped.wait, 3)

    async def test_timeout_waits_for_read_worker_before_database_close(self):
        started, stopped = threading.Event(), threading.Event()

        def wait_for_cancel(root_id, cancel=None):
            started.set()
            cancel.wait(3)
            self.service.root(root_id)
            stopped.set()
            return {}

        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(self.service.io(wait_for_cancel, self.id), timeout=0.05)
        self.assertTrue(started.is_set())
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.service.active_count, 0)

    def test_restart_marks_running_analysis_interrupted(self):
        self.service._write(
            "INSERT INTO jobs(id,root_id,created_at,status) VALUES(?,?,?,'running')",
            ("interrupted", self.id, "2026-10-12"),
        )
        other = WorkspaceService(self.folder / "workspace.sqlite3")
        self.addCleanup(other.close)
        self.assertEqual(other.jobs(self.id)[0]["status"], "interrupted")

    async def test_analysis_history_readonly(self):
        before = self.hashes()
        self.service.start_analysis(self.id, True)
        await self.service.wait_analysis()
        job = self.service.jobs(self.id)[0]
        self.assertEqual(job["status"], "completed")
        report = job["report"]
        self.assertEqual(report["duplicates"][0]["paths"], ["copy.md", "notes.md"])
        self.assertGreaterEqual(report["disk"]["total"], report["disk"]["free"])
        self.assertGreaterEqual(report["logical_bytes"], 50)
        self.assertGreaterEqual(report["skipped"], 1)
        self.assertTrue(any(d["hint"] == "cache" for d in report["directories"]))
        self.assertEqual(self.hashes(), before)

    async def test_cancel_limits_shutdown(self):
        job = self.service.start_analysis(self.id, False)
        self.service.cancel(job["id"])
        await self.service.wait_analysis()
        self.assertEqual(self.service.jobs(self.id)[0]["status"], "cancelled")
        from herta_agent.workspace.analysis import scan

        report = scan(self.service, self.id, False, threading.Event(), max_entries=1)
        self.assertTrue(report["partial"])
        self.assertLessEqual(report["entries"], 1)
        self.service.start_analysis(self.id, True)
        await self.service.shutdown()
        self.assertEqual(self.service.active_count, 0)

    async def test_api_token_and_validation(self):
        app = create_app(
            ServiceSettings(
                provider="demo",
                db_path=self.folder / "sessions.sqlite3",
                workspace_token="desktop-only",
            )
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                self.assertEqual((await client.get("/workspace/roots")).status_code, 401)
                headers = {"Authorization": "Bearer desktop-only"}
                response = await client.post(
                    "/workspace/roots", headers=headers, json={"path": str(self.root)}
                )
                self.assertEqual(response.status_code, 201)
                self.assertFalse(response.json()["shared"])
                self.assertNotIn(
                    "desktop-only", repr(ServiceSettings(workspace_token="desktop-only"))
                )
                response = await client.post(
                    "/workspace/roots",
                    headers=headers,
                    json={"path": str(self.root), "extra": True},
                )
                self.assertEqual(response.status_code, 422)

    async def test_existing_http_agent_loop_reads_only_shared_roots(self):
        root_id = self.id
        feedback = []

        class Provider:
            async def complete(self, messages, *, tools=()):
                if messages[-1].role == "tool":
                    feedback.append(json.loads(messages[-1].content))
                    return ModelReply(message=Message(role="assistant", content="本地夹具完成"))
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(
                            ToolCall(
                                id="file",
                                name="read_workspace_text",
                                arguments=json.dumps({"root_id": root_id, "path": "notes.md"}),
                            ),
                        ),
                    )
                )

        app = create_app(
            ServiceSettings(db_path=self.folder / "sessions.sqlite3"), provider=Provider()
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local"
            ) as client:
                session = (await client.post("/sessions", json={})).json()["session_id"]
                self.service.share(self.id, True)
                first = await client.post(
                    f"/sessions/{session}/runs", json={"text": "读取测试笔记"}
                )
                self.assertIn("run.completed", first.text)
                self.assertTrue(feedback[-1]["ok"])
                self.assertIn("第一行", feedback[-1]["data"]["text"])
                self.service.share(self.id, False)
                second = await client.post(f"/sessions/{session}/runs", json={"text": "再次读取"})
                self.assertIn("run.completed", second.text)
                self.assertFalse(feedback[-1]["ok"])
