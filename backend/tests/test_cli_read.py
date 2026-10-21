"""Exercise the real CLI and filesystem with explicitly offline provider responses."""

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

from herta_agent.cli import main
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.coding.read_file import read_file
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class CLIReadTests(unittest.TestCase):
    def invoke(self, root: Path, path: str) -> subprocess.CompletedProcess:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("HERTA_") and key != "DEEPSEEK_API_KEY"
        }
        env.update(
            PYTHONPATH=str(Path(__file__).resolve().parents[1]),
            PYTHONIOENCODING="utf-8",
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "herta_agent",
                "--repo",
                str(root),
                "--demo-read-file",
                path,
                "--message",
                "请读取这份笔记，展示内容。",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def feedback(self, result: subprocess.CompletedProcess) -> dict:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("离线", result.stdout)
        self.assertIn("[steps=2]", result.stdout)
        reply = next(line for line in result.stdout.splitlines() if line.startswith("Assistant:"))
        return json.loads(reply[reply.index("{") :])

    def test_module_reads_real_utf8_markdown_and_returns_numbered_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            note = root / "notes" / "演示.md"
            note.parent.mkdir()
            note.write_text("# 学习笔记\n先理解调用链。\n再补一个测试。\n", encoding="utf-8")

            result = self.feedback(self.invoke(root, "notes/演示.md"))

            self.assertTrue(result["ok"])
            self.assertEqual(
                result["data"],
                {
                    "path": "notes/演示.md",
                    "sha256": hashlib.sha256(note.read_bytes()).hexdigest(),
                    "lines": [
                        {"line": 1, "text": "# 学习笔记"},
                        {"line": 2, "text": "先理解调用链。"},
                        {"line": 3, "text": "再补一个测试。"},
                    ],
                    "truncated": False,
                    "next_line": None,
                },
            )
            self.assertEqual(
                note.read_text(encoding="utf-8"), "# 学习笔记\n先理解调用链。\n再补一个测试。\n"
            )

    def test_missing_excluded_outside_and_binary_paths_return_tool_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "repo"
            root.mkdir()
            (parent / "outside.txt").write_text("OUTSIDE_FIXTURE", encoding="utf-8")
            (root / ".env").write_text("FIXTURE_ONLY", encoding="utf-8")
            (root / "binary.txt").write_bytes(b"\x00\xff")
            for path, code in (
                ("missing.md", "path_missing"),
                ("../outside.txt", "path_denied"),
                (str(parent / "outside.txt"), "path_denied"),
                (".env", "path_denied"),
                ("binary.txt", "not_text"),
                (".", "not_file"),
            ):
                with self.subTest(path=path):
                    invocation = self.invoke(root, path)
                    result = self.feedback(invocation)
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["error"]["code"], code)
                    self.assertNotIn("OUTSIDE_FIXTURE", invocation.stdout)
                    self.assertNotIn("FIXTURE_ONLY", invocation.stdout)

    def test_multibyte_file_is_paginated_before_executor_result_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "long.md").write_text(("黑" * 300 + "\n") * 120, encoding="utf-8")
            result = self.feedback(self.invoke(root, "long.md"))
            self.assertTrue(result["ok"])
            self.assertTrue(result["data"]["truncated"])
            self.assertGreater(len(result["data"]["lines"]), 0)
            self.assertLess(len(result["data"]["lines"]), 120)
            self.assertEqual(result["data"]["lines"][0], {"line": 1, "text": "黑" * 300})
            self.assertEqual(result["data"]["next_line"], result["data"]["lines"][-1]["line"] + 1)
            self.assertLess(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), 64_000)

    def test_openai_adapter_sends_read_results_and_schema_without_legacy_services(self):
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "read_note",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"note.md","start_line":2,"end_line":2}',
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": "固定HTTP夹具：已收到第二行。"}
                finish = "stop"
            return httpx.Response(
                200, json={"choices": [{"message": message, "finish_reason": finish}]}
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "note.md").write_text("标题\n真正从磁盘读取的正文\n末行\n", encoding="utf-8")
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
                contextlib.redirect_stdout(output),
            ):
                main(["--provider", "openai", "--repo", str(root), "--message", "读取第二行"])

            self.assertTrue(client.is_closed)
            self.assertEqual(len(requests), 2)
            self.assertEqual(
                [tool["function"]["name"] for tool in requests[0]["tools"]],
                ["read_file", "grep_code", "edit_file"],
            )
            self.assertEqual(
                [message["role"] for message in requests[1]["messages"]],
                ["system", "user", "assistant", "tool"],
            )
            feedback = requests[1]["messages"][-1]
            self.assertEqual(feedback["tool_call_id"], "read_note")
            self.assertEqual(
                json.loads(feedback["content"])["data"]["lines"],
                [{"line": 2, "text": "真正从磁盘读取的正文"}],
            )
            self.assertIn("固定HTTP夹具：已收到第二行。", output.getvalue())
            self.assertIn("[steps=2]", output.getvalue())


class ReadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "repo"
        self.root.mkdir()
        self.repo = Repository(self.root)
        registry = ToolRegistry()
        registry.register(read_file(self.repo))
        self.executor = ToolExecutor(registry)

    async def execute(self, **parameters):
        return await self.executor.execute(
            ToolCall(id="read", name="read_file", arguments=json.dumps(parameters))
        )

    async def test_invalid_utf8_is_rejected_and_oversized_file_is_not_a_partial_success(self):
        (self.root / "invalid.md").write_bytes(b"valid\n\xff")
        result = await self.execute(path="invalid.md")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "not_text")
        (self.root / "oversized.md").write_bytes(b"row\n" * 400_000)
        result = await self.execute(path="oversized.md")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "file_too_large")

    async def test_strict_argument_validation_happens_before_disk_lookup(self):
        with patch.object(self.repo, "path", side_effect=AssertionError("must not read")):
            result = await self.execute(path="note.md", start_line=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_arguments")

    async def test_zero_start_line_is_rejected_before_disk_lookup(self):
        with patch.object(self.repo, "path", side_effect=AssertionError("must not read")) as lookup:
            result = await self.execute(path="note.md", start_line=0)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "invalid_arguments")
        lookup.assert_not_called()

    async def test_reversed_range_and_oversized_line_are_explicit_errors(self):
        (self.root / "note.md").write_text("first\nsecond\n", encoding="utf-8")
        reversed_range = await self.execute(path="note.md", start_line=2, end_line=1)
        self.assertEqual(reversed_range.error.code, "invalid_range")
        (self.root / "line.md").write_text("a" * 40_000, encoding="utf-8")
        long_line = await self.execute(path="line.md")
        self.assertEqual(long_line.error.code, "line_too_long")

    async def test_resolved_outside_link_and_windows_aliases_are_rejected(self):
        for path in ("note.md:stream", "CON.txt", "note.md.", ".ENV.local"):
            with self.subTest(path=path):
                self.assertEqual((await self.execute(path=path)).error.code, "path_denied")
        outside = self.parent / "outside.md"
        outside.write_text("OUTSIDE_FIXTURE", encoding="utf-8")
        try:
            os.symlink(outside, self.root / "link.md")
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        self.assertEqual((await self.execute(path="link.md")).error.code, "path_denied")

    async def test_real_handler_can_cancel_its_wait_and_eventual_worker_closes(self):
        reader = importlib.import_module("herta_agent.tools.coding.read_file")
        original = reader._read_file
        (self.root / "note.md").write_text("real file", encoding="utf-8")
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def delayed_read(*args):
            started.set()
            try:
                release.wait(2)  # Bounded even if a broken handler blocks the event loop.
                return original(*args)
            finally:
                finished.set()

        with patch.object(reader, "_read_file", side_effect=delayed_read):
            task = asyncio.create_task(self.execute(path="note.md"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))

    async def test_next_line_continues_without_skipping_any_complete_line(self):
        (self.root / "lines.md").write_text("line\n" * 500, encoding="utf-8")
        first = await self.execute(path="lines.md")
        self.assertEqual(len(first.data["lines"]), 400)
        self.assertEqual(first.data["next_line"], 401)
        second = await self.execute(path="lines.md", start_line=401)
        self.assertEqual(second.data["lines"][0], {"line": 401, "text": "line"})
        self.assertEqual(second.data["lines"][-1], {"line": 500, "text": "line"})
        self.assertFalse(second.data["truncated"])
        self.assertIsNone(second.data["next_line"])
