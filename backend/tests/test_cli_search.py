"""Real filesystem search and the existing CLI loop; model responses stay local."""

import asyncio
import contextlib
import importlib
import io
import json
import os
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


class SearchToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "repo"
        self.root.mkdir()
        self.repo = Repository(self.root)
        self.root = self.repo.root
        self.agent = create_agent(DemoProvider(), RunSettings(), self.repo)

    async def search(self, **parameters):
        return await self.agent.executor.execute(
            ToolCall(id="find", name="grep_code", arguments=json.dumps(parameters))
        )

    async def test_search_returns_real_paths_lines_and_literal_case_sensitive_matches(self):
        (self.root / "billing.py").write_text(
            "# billing\ndef add_tax(price):\n    return price * 1.1\n", encoding="utf-8"
        )
        found = await self.search(query="def add_tax")
        self.assertTrue(found.ok)
        self.assertEqual(
            found.data["matches"],
            [{"path": "billing.py", "line": 2, "text": "def add_tax(price):"}],
        )
        self.assertFalse(found.data["truncated"])
        (self.root / "literal.txt").write_text("value[0]\nvalue0\n", encoding="utf-8")
        literal = await self.search(query="[0]", path="literal.txt")
        self.assertEqual(literal.data["matches"][0]["line"], 1)
        different_case = await self.search(query="ADD_TAX", path="billing.py")
        self.assertTrue(different_case.ok)
        self.assertEqual(different_case.data["matches"], [])

    async def test_result_limit_and_multibyte_preview_budget_are_explicit(self):
        (self.root / "many.txt").write_text("needle\n" * 5, encoding="utf-8")
        limited = await self.search(query="needle", limit=2)
        self.assertTrue(limited.ok)
        self.assertEqual([hit["line"] for hit in limited.data["matches"]], [1, 2])
        self.assertTrue(limited.data["truncated"])
        (self.root / "chinese.txt").write_text(("黑" * 1200 + "\n") * 20, encoding="utf-8")
        chinese = await self.search(query="黑", path="chinese.txt", limit=100)
        self.assertTrue(chinese.ok)
        self.assertTrue(chinese.data["truncated"])
        self.assertGreater(len(chinese.data["matches"]), 0)
        self.assertLess(len(chinese.data["matches"]), 20)
        self.assertTrue(chinese.data["matches"][0]["line_truncated"])
        self.assertLess(len(chinese.to_json().encode("utf-8")), 10_000)

    async def test_internal_paths_are_excluded_and_unreadable_text_is_counted(self):
        (self.root / "visible.py").write_text("needle\n", encoding="utf-8")
        for name in (".git", ".local", "node_modules"):
            directory = self.root / name
            directory.mkdir()
            (directory / "hidden.txt").write_text("needle\n", encoding="utf-8")
        (self.root / ".env.local").write_text("needle\n", encoding="utf-8")
        (self.root / "binary.txt").write_bytes(b"needle\x00")
        (self.root / "invalid.txt").write_bytes(b"needle\xff")
        (self.root / "oversized.txt").write_bytes(b"needle\n" * 160_000)
        found = await self.search(query="needle")
        self.assertTrue(found.ok)
        self.assertEqual(
            found.data["matches"], [{"path": "visible.py", "line": 1, "text": "needle"}]
        )
        self.assertEqual(found.data["skipped_files"], 3)

    async def test_missing_outside_paths_and_bad_arguments_do_not_search(self):
        for parameters, code in (
            ({"query": "needle", "path": "missing"}, "path_missing"),
            ({"query": "needle", "path": ".."}, "path_denied"),
            ({"query": "needle", "path": ".git"}, "path_denied"),
            ({"query": ""}, "invalid_arguments"),
            ({"query": "needle", "limit": 0}, "invalid_arguments"),
        ):
            with self.subTest(parameters=parameters):
                result = await self.search(**parameters)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)

    async def test_total_read_budget_returns_incomplete_instead_of_false_no_match(self):
        for number in range(17):
            (self.root / f"file{number:02}.txt").write_bytes(b"a" * (1024 * 1024))
        result = await self.search(query="absent")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["matches"], [])
        self.assertTrue(result.data["truncated"])

    async def test_outside_links_are_not_traversed_or_read(self):
        outside = self.parent / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("OUTSIDE_FIXTURE", encoding="utf-8")
        (self.root / "visible.txt").write_text("ordinary", encoding="utf-8")
        try:
            os.symlink(outside, self.root / "linked", target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        result = await self.search(query="OUTSIDE_FIXTURE")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["matches"], [])
        denied = await self.search(query="OUTSIDE_FIXTURE", path="linked")
        self.assertEqual(denied.error.code, "path_denied")

    async def test_nonregular_directory_entries_are_not_opened(self):
        module = importlib.import_module("herta_agent.tools.coding.grep_code")
        ordinary = self.root / "ordinary.txt"
        nonregular = self.root / "pipe-fixture"
        ordinary.write_text("needle", encoding="utf-8")
        nonregular.write_text("needle", encoding="utf-8")
        is_file = Path.is_file

        def file_type(path):
            # Windows cannot make a POSIX FIFO: only its non-regular metadata is simulated.
            return False if path == nonregular else is_file(path)

        with (
            patch.object(Path, "is_file", file_type),
            patch.object(module, "read_bounded_bytes", wraps=module.read_bounded_bytes) as reads,
        ):
            result = await self.search(query="needle")
        self.assertTrue(result.ok)
        self.assertEqual([hit["path"] for hit in result.data["matches"]], ["ordinary.txt"])
        self.assertEqual([call.args[0] for call in reads.call_args_list], [ordinary])

    async def test_cancelled_search_stops_between_files_and_worker_finishes(self):
        module = importlib.import_module("herta_agent.tools.coding.grep_code")
        original = module.read_bounded_bytes
        original_search = module._search
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        opened = []
        (self.root / "a.txt").write_text("needle", encoding="utf-8")
        (self.root / "b.txt").write_text("needle", encoding="utf-8")

        def delayed_read(path, **kwargs):
            opened.append(path.name)
            started.set()
            release.wait(2)
            return original(path, **kwargs)

        def tracked_search(*args):
            try:
                return original_search(*args)
            finally:
                finished.set()

        with (
            patch.object(module, "read_bounded_bytes", side_effect=delayed_read),
            patch.object(module, "_search", side_effect=tracked_search),
        ):
            task = asyncio.create_task(self.search(query="needle"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
            # Wait for the entire search, so a late second read cannot escape the assertion.
        self.assertEqual(opened, ["a.txt"])


class SearchReadCLITests(unittest.TestCase):
    def test_cli_search_results_select_the_read_path_in_the_same_loop(self):
        bodies = []

        def respond(request):
            body = json.loads(request.content)
            bodies.append(body)
            if len(bodies) == 1:
                name, call_id, arguments = "grep_code", "find", {"query": "def add_tax"}
            elif len(bodies) == 2:
                hit = json.loads(body["messages"][-1]["content"])["data"]["matches"][0]
                name, call_id, arguments = (
                    "read_file",
                    "read",
                    {"path": hit["path"], "start_line": hit["line"], "end_line": hit["line"] + 1},
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "固定HTTP夹具：已收到函数正文。",
                                },
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

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "billing.py").write_text(
                "# billing\ndef add_tax(price):\n    return price * 1.1\n", encoding="utf-8"
            )
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
                main(
                    ["--provider", "openai", "--repo", str(root), "--message", "找到并读取add_tax"]
                )
            self.assertTrue(client.is_closed)
            self.assertEqual(len(bodies), 3)
            self.assertEqual(
                [tool["function"]["name"] for tool in bodies[0]["tools"]],
                ["read_file", "grep_code", "edit_file"],
            )
            self.assertEqual(
                [message["role"] for message in bodies[-1]["messages"]],
                ["system", "user", "assistant", "tool", "assistant", "tool"],
            )
            self.assertEqual(bodies[-1]["messages"][-1]["tool_call_id"], "read")
            self.assertEqual(
                json.loads(bodies[-1]["messages"][-1]["content"])["data"]["lines"],
                [
                    {"line": 2, "text": "def add_tax(price):"},
                    {"line": 3, "text": "    return price * 1.1"},
                ],
            )
            self.assertIn("[steps=3]", output.getvalue())
