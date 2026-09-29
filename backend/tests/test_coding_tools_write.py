import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.apply_patch import apply_patch
from herta_agent.tools.coding.run_tests import run_tests
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class WriteToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_patch_sql_comment_hunk(self):
        (self.ws.root / "query.sql").write_text("-- old\nSELECT 1;\n", encoding="utf-8")
        patch = "--- a/query.sql\n+++ b/query.sql\n@@ -1,2 +1,2 @@\n--- old\n+-- new\n SELECT 1;\n"
        result = await self.execute("apply_patch", patch=patch)
        self.assertTrue(result.ok)
        self.assertEqual((self.ws.root / "query.sql").read_text(), "-- new\nSELECT 1;\n")

    async def test_header_only_patch_cannot_claim_applied(self):
        empty = await self.execute("apply_patch", patch="diff --git a/x b/x\n")
        self.assertFalse(empty.ok)

    async def test_subtest_counts_do_not_become_negative(self):
        (self.ws.root / "tests/test_calc.py").write_text(
            "import unittest\nclass Subtests(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        for value in (1, 2):\n"
            "            with self.subTest(value=value):\n"
            "                self.assertEqual(value, 0)\n"
            "    def test_skips(self):\n"
            "        for value in (1, 2):\n"
            "            with self.subTest(value=value):\n"
            '                self.skipTest("skip subtest")\n',
            encoding="utf-8",
        )
        result = (await self.execute("run_tests")).data
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["skipped_subtests"], 2)
        self.assertEqual(result["status"], "failed")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        (self.source / "calc.py").write_text("def value():\n    return 1\n", encoding="utf-8")
        (self.source / "tests").mkdir()
        (self.source / "tests/test_calc.py").write_text(
            "import unittest\nfrom calc import value\nclass Test(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 2)\n",  # noqa: E501
            encoding="utf-8",
        )
        self.ws = Workspace.open(self.source)
        registry = ToolRegistry()
        registry.register(apply_patch(self.ws))
        registry.register(run_tests(self.ws, timeout=2))
        self.executor = ToolExecutor(registry)

    async def execute(self, name, **args):
        return await self.executor.execute(ToolCall(id="x", name=name, arguments=json.dumps(args)))

    async def test_conflicts_and_paths_leave_all_files_unchanged(self):
        good = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n"  # noqa: E501
        bad = good + "--- a/missing.py\n+++ b/missing.py\n@@ -1 +1 @@\n-no\n+yes\n"
        result = await self.execute("apply_patch", patch=bad)
        self.assertFalse(result.ok)
        self.assertIn("return 1", (self.ws.root / "calc.py").read_text())
        for path in ("../calc.py", ".git/config", "C:/outside.py"):
            result = await self.execute(
                "apply_patch", patch=f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+bad\n"
            )
            self.assertFalse(result.ok)
        result = await self.execute("apply_patch", patch=good)
        self.assertTrue(result.ok)
        self.assertIn("return 2", (self.ws.root / "calc.py").read_text())
        self.assertIn("return 1", (self.source / "calc.py").read_text())

    async def test_real_failed_and_passed_counts_and_details(self):
        failed = await self.execute("run_tests")
        self.assertTrue(failed.ok)  # Tool ran; test outcome is separately failed.
        self.assertEqual(failed.data["status"], "failed")
        self.assertEqual(failed.data["failed"], 1)
        self.assertIn("AssertionError", failed.data["output"])
        (self.ws.root / "calc.py").write_text("def value():\n    return 2\n", encoding="utf-8")
        passed = await self.execute("run_tests")
        self.assertEqual(passed.data["status"], "passed")
        self.assertEqual(passed.data["passed"], 1)

    async def test_timeout_and_cancel_reap_test_process(self):
        (self.ws.root / "tests/test_calc.py").write_text(
            'import os,time\nfrom pathlib import Path\nPath("pid.txt").write_text(str(os.getpid()))\ntime.sleep(60)\n',  # noqa: E501
            encoding="utf-8",
        )
        timed = await self.execute("run_tests")
        self.assertEqual(timed.error.code, "timeout")
        pid = int((self.ws.root / "pid.txt").read_text())
        with self.assertRaises(OSError):
            os.kill(pid, 0)
        (self.ws.root / "pid.txt").unlink()
        task = asyncio.create_task(self.execute("run_tests"))
        async with asyncio.timeout(3):
            while not (self.ws.root / "pid.txt").exists():  # noqa: ASYNC110 - process readiness
                await asyncio.sleep(0.02)
        pid = int((self.ws.root / "pid.txt").read_text())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(OSError):
            os.kill(pid, 0)

    def test_workspace_reopens_without_overwriting_and_excludes_secrets(self):
        (self.source / ".env").write_text("secret", encoding="utf-8")
        (self.ws.root / "calc.py").write_text("edited", encoding="utf-8")
        other = Workspace.open(self.source)
        self.assertEqual((other.root / "calc.py").read_text(), "edited")
        self.assertFalse((other.root / ".env").exists())
