import json
import os
import tempfile
import unittest
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding import coding_registry
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.executor import ToolExecutor


class ReadToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        (self.root / "code.py").write_text("first\nneedle\nlast\n", encoding="utf-8")
        self.executor = ToolExecutor(coding_registry(Repository(self.root)))

    async def execute(self, name, **args):
        return await self.executor.execute(ToolCall(id="x", name=name, arguments=json.dumps(args)))

    async def test_read_lines_search_and_exclusions(self):
        result = await self.execute("read_file", path="code.py", start_line=2, end_line=2)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["lines"], [{"line": 2, "text": "needle"}])
        for name in (".git", ".venv", "node_modules"):
            (self.root / name).mkdir()
        listing = await self.execute("list_directory", path=".")
        self.assertEqual([x["path"] for x in listing.data["entries"]], ["code.py"])
        found = await self.execute("grep_code", query="needle")
        self.assertEqual(found.data["matches"], [{"path": "code.py", "line": 2, "text": "needle"}])

    async def test_escape_missing_and_outside_symlink_rejected(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        for path in ("../outside.txt", str(outside), "C:\\Windows\\win.ini", "code.py:stream"):
            for tool in ("read_file", "list_directory", "grep_code"):
                args = {"path": path, **({"query": "private"} if tool == "grep_code" else {})}
                self.assertEqual((await self.execute(tool, **args)).error.code, "path_denied")
        self.assertEqual(
            (await self.execute("read_file", path="missing")).error.code, "path_missing"
        )
        os.symlink(outside, self.root / "escape.txt")
        self.assertEqual(
            (await self.execute("read_file", path="escape.txt")).error.code, "path_denied"
        )

    async def test_limits_are_explicit(self):
        (self.root / "large.txt").write_text("needle\n" * 5000, encoding="utf-8")
        result = await self.execute("read_file", path="large.txt")
        self.assertTrue(result.data["truncated"])
        result = await self.execute("grep_code", query="needle", limit=2)
        self.assertEqual(len(result.data["matches"]), 2)
        self.assertTrue(result.data["truncated"])
