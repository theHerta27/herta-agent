"""Confirmed creation uses real temporary files and the existing executor/approval/loop."""

import asyncio
import contextlib
import hashlib
import importlib
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from herta_agent.cli import create_agent
from herta_agent.config import RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


async def allow_fixture(spec, parameters):
    return True  # Test-only; the product still requires TerminalApproval.


class CreateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "repo"
        self.root.mkdir()
        self.repo = Repository(self.root)

    def agent(self, authorize=None):
        return create_agent(DemoProvider(), RunSettings(), self.repo, authorize=authorize)

    async def execute(self, *, authorize=allow_fixture, **arguments):
        return await self.agent(authorize).executor.execute(
            ToolCall(id="create", name="create_file", arguments=json.dumps(arguments))
        )

    async def test_default_denial_creates_nothing(self):
        result = await self.execute(authorize=None, path="new.py", content="answer = 42\n")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "permission_denied")
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_terminal_preview_precedes_yes_and_no_keeps_directory_unchanged(self):
        for answer in ("no", "yes"):
            with self.subTest(answer=answer):
                stream = io.StringIO()
                target = self.root / (answer + ".py")

                def confirm(prompt, target=target, stream=stream, answer=answer):
                    self.assertFalse(target.exists())
                    self.assertIn("--- /dev/null", stream.getvalue())
                    self.assertIn("+answer = 42", stream.getvalue())
                    return answer

                with (
                    contextlib.redirect_stdout(stream),
                    patch("builtins.input", side_effect=confirm),
                ):
                    result = await self.execute(
                        authorize=TerminalApproval(self.repo),
                        path=target.name,
                        content="answer = 42\n",
                    )
                self.assertEqual(result.ok, answer == "yes")
                if answer == "yes":
                    self.assertEqual(target.read_bytes(), b"answer = 42\n")
                    self.assertTrue(result.data["created"])
                else:
                    self.assertEqual(result.error.code, "permission_denied")
                    self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".coding-create-*")), [])

    async def test_empty_and_crlf_unicode_content_are_exact_and_readable(self):
        for name, content in (("empty.py", ""), ("笔记.md", "第一行\r\n第二行\r\n")):
            with self.subTest(path=name):
                result = await self.execute(path=name, content=content)
                self.assertTrue(result.ok, result.error)
                actual = (self.root / name).read_bytes()
                self.assertEqual(actual, content.encode("utf-8"))
                self.assertEqual(result.data["after_sha256"], hashlib.sha256(actual).hexdigest())
                self.assertEqual((self.root / name).stat().st_nlink, 1)
        self.assertEqual(list(self.root.glob(".coding-create-*")), [])

    async def test_existing_file_or_directory_is_never_overwritten(self):
        target = self.root / "keep.py"
        target.write_bytes(b"ORIGINAL_FIXTURE")
        (self.root / "folder").mkdir()
        for path in ("keep.py", "folder"):
            result = await self.execute(path=path, content="replacement")
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "create_conflict")
        self.assertEqual(target.read_bytes(), b"ORIGINAL_FIXTURE")
        self.assertTrue((self.root / "folder").is_dir())

    async def test_file_appearing_during_confirmation_is_preserved(self):
        target = self.root / "new.py"

        def another_writer(prompt):
            target.write_bytes(b"OTHER_WRITER_FIXTURE")
            return "yes"

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("builtins.input", side_effect=another_writer),
        ):
            result = await self.execute(
                authorize=TerminalApproval(self.repo), path="new.py", content="ours"
            )
        self.assertEqual(result.error.code, "create_conflict")
        self.assertEqual(target.read_bytes(), b"OTHER_WRITER_FIXTURE")
        self.assertEqual(list(self.root.glob(".coding-create-*")), [])

    async def test_collision_at_publish_is_preserved_and_staging_file_is_removed(self):
        module = importlib.import_module("herta_agent.tools.coding.create_file")
        actual_link = os.link
        target = self.root / "new.py"

        def race(source, destination, **kwargs):
            Path(destination).write_bytes(b"LATE_WRITER_FIXTURE")
            return actual_link(source, destination, **kwargs)

        with patch.object(module.os, "link", side_effect=race):
            result = await self.execute(path="new.py", content="ours")
        self.assertEqual(result.error.code, "create_conflict")
        self.assertEqual(target.read_bytes(), b"LATE_WRITER_FIXTURE")
        self.assertEqual(list(self.root.glob(".coding-create-*")), [])

    async def test_unsupported_publish_fails_without_a_fallback_write(self):
        module = importlib.import_module("herta_agent.tools.coding.create_file")
        with patch.object(module.os, "link", side_effect=OSError("unsupported fixture")):
            result = await self.execute(path="new.py", content="ours")
        self.assertEqual(result.error.code, "create_write_failed")
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_cleanup_error_is_honest_about_an_already_created_target(self):
        module = importlib.import_module("herta_agent.tools.coding.create_file")
        actual_unlink = os.unlink

        def fail_cleanup(path, *args, **kwargs):
            if Path(path).name.startswith(".coding-create-"):
                raise PermissionError("cleanup fixture")
            return actual_unlink(path, *args, **kwargs)

        with patch.object(module.os, "unlink", side_effect=fail_cleanup):
            result = await self.execute(path="new.py", content="created")
        self.assertEqual(result.error.code, "create_cleanup_failed")
        self.assertIn("可能已创建", result.error.message)
        self.assertEqual((self.root / "new.py").read_bytes(), b"created")

    async def test_path_content_and_preview_boundaries_do_not_create_files(self):
        cases = [
            ({"path": "../escape.py", "content": "x"}, "path_denied"),
            ({"path": str(self.root / "absolute.py"), "content": "x"}, "path_denied"),
            ({"path": ".env", "content": "x"}, "path_denied"),
            ({"path": ".git/new.py", "content": "x"}, "path_denied"),
            ({"path": "CON.py", "content": "x"}, "path_denied"),
            ({"path": "new.py:stream", "content": "x"}, "path_denied"),
            ({"path": "new.py.", "content": "x"}, "path_denied"),
            ({"path": "new\n.py", "content": "x"}, "path_denied"),
            ({"path": "missing/new.py", "content": "x"}, "parent_missing"),
            ({"path": "new.py", "content": "x\x00y"}, "not_text"),
            ({"path": "new.py", "content": "\ud800"}, "invalid_arguments"),
            ({"path": "new.py", "content": "x" * 20000}, "create_too_large"),
            ({"path": "new.py", "content": "x" * 32001}, "invalid_arguments"),
            ({"path": "new.py", "content": 5}, "invalid_arguments"),
        ]
        for arguments, code in cases:
            with self.subTest(path=repr(arguments["path"]), code=code):
                result = await self.execute(**arguments)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse((self.parent / "escape.py").exists())

    async def test_links_dangling_links_and_cycles_are_rejected(self):
        real = self.root / "real"
        real.mkdir()
        try:
            (self.root / "linked").symlink_to(real, target_is_directory=True)
            (self.root / "dangling.py").symlink_to(real / "missing.py")
            (self.root / "a.py").symlink_to("b.py")
            (self.root / "b.py").symlink_to("a.py")
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        for path in ("linked/new.py", "dangling.py", "a.py"):
            result = await self.execute(path=path, content="ours")
            self.assertEqual(result.error.code, "path_denied")
        self.assertEqual(list(real.iterdir()), [])

    async def test_cancelled_preparation_never_performs_a_late_create(self):
        module = importlib.import_module("herta_agent.tools.coding.create_file")
        prepare = module.prepare_create
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def delayed(*args):
            started.set()
            try:
                release.wait(2)
                return prepare(*args)
            finally:
                finished.set()

        with patch.object(module, "prepare_create", side_effect=delayed):
            task = asyncio.create_task(self.execute(path="new.py", content="ours"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_original_loop_creates_then_reads_the_same_bytes_and_fingerprint(self):
        class CreateReadFixture:
            receipt = None

            async def complete(self, messages, *, tools=()):
                if messages[-1].role == "user":
                    name, arguments = "create_file", {"path": "new.py", "content": "answer = 42\n"}
                else:
                    feedback = json.loads(messages[-1].content)
                    if not feedback["ok"]:
                        return ModelReply(
                            message=Message(role="assistant", content=feedback["error"]["code"])
                        )
                    if messages[-1].tool_call_id == "create_file":
                        self.receipt = feedback["data"]
                        name, arguments = "read_file", {"path": "new.py"}
                    else:
                        return ModelReply(
                            message=Message(role="assistant", content=json.dumps(feedback["data"]))
                        )
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(ToolCall(id=name, name=name, arguments=json.dumps(arguments)),),
                    )
                )

        provider = CreateReadFixture()
        agent = create_agent(provider, RunSettings(), self.repo, authorize=allow_fixture)
        result = await agent.run(Session(), "创建并回读")
        self.assertEqual(result.steps, 3)
        data = json.loads(result.reply)
        self.assertEqual(data["lines"], [{"line": 1, "text": "answer = 42"}])
        self.assertEqual(data["sha256"], provider.receipt["after_sha256"])
        self.assertEqual((self.root / "new.py").read_bytes(), b"answer = 42\n")
