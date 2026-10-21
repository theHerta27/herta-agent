"""Single-file edits through the real CLI/loop; all model traffic stays in MockTransport."""

import asyncio
import contextlib
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.cli import create_agent, main
from herta_agent.config import RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


class CLIEditTests(unittest.TestCase):
    def test_one_sigint_during_confirmation_refuses_without_stalled_input(self):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(Path(__file__).with_name("cli_edit_interrupt_probe.py")),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=6,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("INPUT_STALLED", result.stdout)
        self.assertIn("VERDICT:permission_denied", result.stdout)
        self.assertIn("UNCHANGED:True", result.stdout)

    def test_read_returns_fingerprint_of_actual_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            content = b"first\r\nsecond\r\n"
            (root / "note.py").write_bytes(content)
            agent = create_agent(DemoProvider(), RunSettings(), Repository(root))
            result = asyncio.run(
                agent.executor.execute(
                    ToolCall(id="read", name="read_file", arguments='{"path":"note.py"}')
                )
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.data.get("sha256"), hashlib.sha256(content).hexdigest())

    def test_edit_is_denied_without_an_authorizer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = b"value = 1\n"
            target = root / "note.py"
            target.write_bytes(before)
            agent = create_agent(DemoProvider(), RunSettings(), Repository(root))
            result = asyncio.run(
                agent.executor.execute(
                    ToolCall(
                        id="edit",
                        name="edit_file",
                        arguments=json.dumps(
                            {
                                "path": "note.py",
                                "old_text": "value = 1",
                                "new_text": "value = 2",
                                "expected_sha256": hashlib.sha256(before).hexdigest(),
                            }
                        ),
                    )
                )
            )
            self.assertEqual(result.error.code, "permission_denied")
            self.assertEqual(target.read_bytes(), before)

    def run_edit_cli(self, approval):
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            step = len(requests)
            if step == 1:
                call_id, name, arguments = "initial", "read_file", {"path": "note.py"}
            elif step == 2:
                data = json.loads(body["messages"][-1]["content"])["data"]
                call_id, name, arguments = (
                    "edit",
                    "edit_file",
                    {
                        "path": "note.py",
                        "old_text": "value = 1",
                        "new_text": "value = 2",
                        "expected_sha256": data.get("sha256", "0" * 64),
                    },
                )
            elif step == 3 and json.loads(body["messages"][-1]["content"])["ok"]:
                call_id, name, arguments = "verify", "read_file", {"path": "note.py"}
            else:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "固定HTTP夹具结束。"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "note.py"
            target.write_bytes(b"value = 1\r\nuntouched = True\r\n")
            client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            output = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {
                        "HERTA_BASE_URL": "https://fixture.invalid/v1",
                        "HERTA_MODEL": "fixture-model",
                        "HERTA_API_KEY": "fixture-key",
                    },
                    clear=True,
                ),
                patch("herta_agent.cli.httpx.AsyncClient", return_value=client),
                patch("builtins.input", side_effect=approval),
                contextlib.redirect_stdout(output),
            ):
                main(
                    [
                        "--provider",
                        "openai",
                        "--repo",
                        str(root),
                        "--message",
                        "把value从1改成2，确认后再读取核对",
                    ]
                )
            self.assertTrue(client.is_closed)
            return target.read_bytes(), requests, output.getvalue()

    def test_cli_confirmation_writes_then_reads_real_result_in_same_loop(self):
        content, requests, output = self.run_edit_cli(["yes"])
        self.assertEqual(content, b"value = 2\r\nuntouched = True\r\n")
        self.assertEqual(len(requests), 4)
        feedback = json.loads(requests[-1]["messages"][-1]["content"])
        self.assertTrue(feedback["ok"])
        self.assertEqual(feedback["data"]["lines"][0], {"line": 1, "text": "value = 2"})
        self.assertIn("-value = 1", output)
        self.assertIn("+value = 2", output)
        self.assertIn("[steps=4]", output)

    def test_cli_denial_blank_and_eof_leave_file_unchanged(self):
        for approval in (["no"], [""], [EOFError()]):
            with self.subTest(approval=approval):
                content, requests, output = self.run_edit_cli(approval)
                self.assertEqual(content, b"value = 1\r\nuntouched = True\r\n")
                feedback = json.loads(requests[-1]["messages"][-1]["content"])
                self.assertEqual(feedback["error"]["code"], "permission_denied")
                self.assertEqual(len(requests), 3)


class EditBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        parent = Path(self.temporary.name)
        (parent / "repo").mkdir()
        self.repo = Repository(parent / "repo")
        self.target = self.repo.root / "note.py"
        self.before = b"value = 1\nuntouched = True\n"
        self.target.write_bytes(self.before)
        self.agent = create_agent(DemoProvider(), RunSettings(), self.repo, authorize=self.approve)

    async def approve(self, spec, parameters):
        return True  # Test-only authority; product CLI uses TerminalApproval.

    async def execute(self, **overrides):
        arguments = {
            "path": "note.py",
            "old_text": "value = 1",
            "new_text": "value = 2",
            "expected_sha256": hashlib.sha256(self.before).hexdigest(),
        }
        arguments.update(overrides)
        return await self.agent.executor.execute(
            ToolCall(id="edit", name="edit_file", arguments=json.dumps(arguments))
        )

    async def test_stale_missing_duplicate_and_overlapping_matches_do_not_write(self):
        for overrides in (
            {"expected_sha256": "0" * 64},
            {"old_text": "missing"},
            {"old_text": "value = 1", "new_text": "value = 1"},
        ):
            with self.subTest(overrides=overrides):
                result = await self.execute(**overrides)
                self.assertEqual(result.error.code, "edit_conflict")
                self.assertEqual(self.target.read_bytes(), self.before)
        for content in (b"repeat repeat", b"aaa"):
            self.before = content
            self.target.write_bytes(content)
            result = await self.execute(
                old_text="repeat" if content.startswith(b"repeat") else "aa"
            )
            self.assertEqual(result.error.code, "edit_conflict")
            self.assertEqual(self.target.read_bytes(), content)

    async def test_unsafe_targets_are_not_written_even_with_test_authority(self):
        outside = self.repo.root.parent / "outside.py"
        outside.write_bytes(b"value = 1\n")
        (self.repo.root / ".env").write_bytes(self.before)
        for path, code in (
            (str(outside), "path_denied"),
            (".env", "path_denied"),
            ("missing.py", "path_missing"),
            (".", "path_denied"),
        ):
            with self.subTest(path=path):
                result = await self.execute(path=path)
                self.assertEqual(result.error.code, code)
        self.assertEqual(outside.read_bytes(), b"value = 1\n")
        self.assertEqual(self.target.read_bytes(), self.before)

    async def test_internal_symlinks_and_hardlinks_are_not_editable(self):
        symlink = self.repo.root / "link.py"
        hardlink = self.repo.root / "hard.py"
        try:
            os.symlink(self.target, symlink)
            os.link(self.target, hardlink)
        except OSError as error:
            self.skipTest(f"Native link fixture unavailable: {error}")
        for path in ("link.py", "hard.py", "note.py"):
            with self.subTest(path=path):
                result = await self.execute(path=path)
                self.assertEqual(result.error.code, "path_denied")
        self.assertEqual(self.target.read_bytes(), self.before)

    async def test_changes_made_while_user_reviews_are_preserved(self):
        self.agent.executor.authorize = TerminalApproval(self.repo)

        def confirm_after_external_edit(prompt):
            self.target.write_bytes(b"external editor changed this\n")
            return "yes"

        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=confirm_after_external_edit),
            contextlib.redirect_stdout(output),
        ):
            result = await self.execute()
        self.assertEqual(result.error.code, "edit_conflict")
        self.assertEqual(self.target.read_bytes(), b"external editor changed this\n")
        self.assertIn("+value = 2", output.getvalue())

    async def test_failed_replace_keeps_original_and_removes_temporary_file(self):
        module = importlib.import_module("herta_agent.tools.coding.edit_file")
        with patch.object(module.os, "replace", side_effect=OSError("fixture write failure")):
            result = await self.execute()
        self.assertEqual(result.error.code, "edit_write_failed")
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(list(self.repo.root.glob(".coding-edit-*")), [])

    async def test_change_during_temporary_write_is_not_overwritten(self):
        module = importlib.import_module("herta_agent.tools.coding.edit_file")
        chmod = os.chmod

        def external_change(path, mode):
            chmod(path, mode)
            self.target.write_bytes(b"newer external content\n")

        with patch.object(module.os, "chmod", side_effect=external_change):
            result = await self.execute()
        self.assertEqual(result.error.code, "edit_conflict")
        self.assertEqual(self.target.read_bytes(), b"newer external content\n")
        self.assertEqual(list(self.repo.root.glob(".coding-edit-*")), [])

    async def test_cancelled_prepare_never_writes_later(self):
        module = importlib.import_module("herta_agent.tools.coding.edit_file")
        prepare = module.prepare_edit
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def delayed_prepare(*args):
            started.set()
            try:
                release.wait(2)
                return prepare(*args)
            finally:
                finished.set()

        with patch.object(module, "prepare_edit", side_effect=delayed_prepare):
            task = asyncio.create_task(self.execute())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(list(self.repo.root.glob(".coding-edit-*")), [])

    async def test_invalid_text_and_unshowable_diff_are_rejected(self):
        result = await self.execute(new_text="bad\u0000text")
        self.assertEqual(result.error.code, "not_text")
        self.assertEqual(self.target.read_bytes(), self.before)
        self.before = b"marker" + b"x" * 10000
        self.target.write_bytes(self.before)
        result = await self.execute(old_text="marker", new_text="other")
        self.assertEqual(result.error.code, "edit_too_large")
        self.assertEqual(self.target.read_bytes(), self.before)

    async def test_terminal_preview_escapes_controls_and_marks_missing_newline(self):
        self.before = b"value = 1\x1b[2J"
        self.target.write_bytes(self.before)
        self.agent.executor.authorize = TerminalApproval(self.repo)
        output = io.StringIO()
        with patch("builtins.input", return_value="no"), contextlib.redirect_stdout(output):
            result = await self.execute()
        self.assertEqual(result.error.code, "permission_denied")
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertNotIn("\x1b", output.getvalue())
        self.assertIn("\\x1b", output.getvalue())
        self.assertIn("No newline at end of file", output.getvalue())

    async def test_newline_only_edit_does_not_hide_carriage_return_in_preview(self):
        self.before = b"value = 1\r\n"
        self.target.write_bytes(self.before)
        self.agent.executor.authorize = TerminalApproval(self.repo)
        output = io.StringIO()
        with patch("builtins.input", return_value="no"), contextlib.redirect_stdout(output):
            result = await self.execute(old_text="\r\n", new_text="\n")
        self.assertEqual(result.error.code, "permission_denied")
        self.assertIn("-value = 1\\r\n", output.getvalue())
        self.assertEqual(self.target.read_bytes(), self.before)

    async def test_readonly_target_is_rejected_without_leaving_readonly_temporary(self):
        self.target.chmod(0o444)
        try:
            result = await self.execute()
            self.assertEqual(result.error.code, "path_denied")
            self.assertEqual(self.target.read_bytes(), self.before)
            self.assertEqual(list(self.repo.root.glob(".coding-edit-*")), [])
        finally:
            self.target.chmod(0o644)
            # Only clean this test's own failed temporary artifacts, if a broken commit left any.
            for temporary in self.repo.root.glob(".coding-edit-*"):
                temporary.chmod(0o644)
                temporary.unlink()
