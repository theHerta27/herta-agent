import json
import tempfile
import unittest
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.run_tests import run_tests
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class PytestRunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        (self.source / "tests").mkdir()
        self.workspace = Workspace.open(self.source)
        (self.workspace.root / "tests").mkdir(exist_ok=True)

    async def execute(self, **args):
        registry = ToolRegistry()
        registry.register(run_tests(self.workspace))
        return await ToolExecutor(registry).execute(
            ToolCall(id="pytest-report", name="run_tests", arguments=json.dumps(args))
        )

    async def test_json_results_include_failure_details_and_skipped_case(self):
        (self.workspace.root / "tests/test_example.py").write_text(
            "import unittest\nclass Example(unittest.TestCase):\n"
            "    def test_good(self): self.assertEqual(2, 2)\n"
            "    def test_bad(self): self.assertEqual(1, 2)\n"
            '    @unittest.skip("deliberate")\n'
            "    def test_skip(self): pass\n",
            encoding="utf-8",
        )
        result = await self.execute()
        self.assertTrue(result.ok)
        self.assertEqual(
            [result.data[k] for k in ("total", "passed", "failed", "skipped")], [3, 1, 1, 1]
        )
        self.assertEqual(result.data["runner"], "pytest")
        bad = next(t for t in result.data["tests"] if t["nodeid"].endswith("test_bad"))
        self.assertEqual(bad["outcome"], "failed")
        self.assertIn("AssertionError", bad["call"]["longrepr"])

    async def test_missing_path_is_an_explicit_error(self):
        result = await self.execute(path="missing")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "path_missing")

    async def test_zero_collected_is_an_explicit_error(self):
        result = await self.execute()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "no_tests_collected")

    async def test_collection_failure_is_not_zero_tests_or_success(self):
        (self.workspace.root / "tests/test_broken.py").write_text(
            'raise RuntimeError("collection broke")\n', encoding="utf-8"
        )
        result = await self.execute()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["status"], "failed")
        self.assertEqual(result.data["collection_errors"], 1)
        self.assertIn("collection broke", json.dumps(result.data["collectors"]))

    async def test_subtest_failures_retain_each_evidence(self):
        (self.workspace.root / "tests/test_sub.py").write_text(
            "import unittest\nclass Example(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        for value in (1, 2):\n"
            "            with self.subTest(value=value): self.assertEqual(value, 0)\n",
            encoding="utf-8",
        )
        result = await self.execute()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["total"], 1)
        self.assertEqual(result.data["failed"], 1)
        subs = result.data["tests"][0]["subtests"]
        self.assertEqual(len(subs), 2)
        self.assertTrue(all(s["outcome"] == "failed" for s in subs))
        self.assertIn("1 != 0", subs[0]["longrepr"])


class PytestReportValidationTests(unittest.TestCase):
    def test_failure_evidence_cannot_be_hidden_by_passed_item(self):
        from herta_agent.runtime.errors import ToolExecutionError
        from herta_agent.tools.coding.run_tests import parse_report

        for evidence in (
            {"call": {"outcome": "failed"}},
            {"setup": {"outcome": "failed"}},
            {"teardown": {"outcome": "failed"}},
            {"subtests": [{"outcome": "failed"}]},
        ):
            report = {
                "exitcode": 0,
                "summary": {"total": 1, "passed": 1},
                "tests": [{"nodeid": "x", "outcome": "passed", **evidence}],
            }
            with self.subTest(evidence=evidence), self.assertRaises(ToolExecutionError):
                parse_report(report, 0)
        with self.assertRaises(ToolExecutionError):
            parse_report(
                {
                    "exitcode": 0,
                    "summary": {"total": 1, "failed": 1},
                    "tests": [{"nodeid": "x", "outcome": "passed"}],
                },
                0,
            )

    def test_corrupt_or_inconsistent_report_cannot_claim_success(self):
        from herta_agent.runtime.errors import ToolExecutionError
        from herta_agent.tools.coding.run_tests import parse_report

        for report in (
            {},
            {"summary": {"total": 1}, "tests": []},
            {"exitcode": 0, "tests": [{"nodeid": "x", "outcome": "unknown"}]},
        ):
            with self.subTest(report=report), self.assertRaises(ToolExecutionError):
                parse_report(report, 0)
