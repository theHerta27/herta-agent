"""Run only tests created by this test module; never run a user's existing project."""

import asyncio
import importlib
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from herta_agent.cli import create_agent
from herta_agent.config import RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


@unittest.skipUnless(sys.platform == "win32", "Windows process-tree execution unit")
class CLITestExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Repository(Path(self.temporary.name))
        self.start = self.repo.root / "tests"
        self.start.mkdir()
        self.agent = create_agent(DemoProvider(), RunSettings(), self.repo, authorize=self.approve)

    async def approve(self, spec, parameters):
        return True  # Dedicated test authority; the product requires terminal confirmation.

    def source(self, body):
        (self.start / "test_sample.py").write_text(body, encoding="utf-8")

    async def execute(self, **overrides):
        arguments = {"path": "tests", "pattern": "test*.py"}
        arguments.update(overrides)
        return await self.agent.executor.execute(
            ToolCall(id="test", name="run_tests", arguments=json.dumps(arguments))
        )

    async def test_success_is_based_on_actual_unittest_report(self):
        self.source(
            "import unittest\nclass Sample(unittest.TestCase):\n"
            " def test_ok(self):\n  self.assertEqual(2 + 2, 4)\n"
        )
        result = await self.execute()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["status"], "passed")
        self.assertEqual(result.data["tests_run"], 1)
        self.assertEqual(result.data["exit_code"], 0)
        self.assertIn("test_ok", result.data["output"])

    async def test_all_subtests_skipped_are_not_reported_passed(self):
        self.source(
            "import unittest\nclass Sample(unittest.TestCase):\n def test_skip(self):\n"
            "  for x in range(3):\n   with self.subTest(x=x):\n    self.skipTest('fixture')\n"
        )
        result = await self.execute()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["status"], "skipped")

    async def test_initialization_failure_is_failed_even_when_no_methods_ran(self):
        for setup in (
            "def setUpModule():\n raise RuntimeError('module setup fixture')\n",
            "class Base(unittest.TestCase):\n @classmethod\n def setUpClass(cls):\n"
            "  raise RuntimeError('class setup fixture')\n",
        ):
            base = "Base" if "class Base" in setup else "unittest.TestCase"
            self.source(
                "import unittest\n"
                + setup
                + f"class Sample({base}):\n def test_never(self):\n  pass\n"
            )
            result = await self.execute()
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.data["tests_run"], 0)
            self.assertEqual(result.data["status"], "failed", result.data["output"])
            self.assertEqual(result.data["error_events"], 1)
            self.assertEqual(result.data["exit_code"], 1)

    async def test_class_setup_skip_is_skipped_even_when_no_methods_ran(self):
        self.source(
            "import unittest\nclass Sample(unittest.TestCase):\n @classmethod\n"
            " def setUpClass(cls):\n  raise unittest.SkipTest('fixture class skip')\n"
            " def test_never(self):\n  pass\n"
        )
        result = await self.execute()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["tests_run"], 0)
        self.assertEqual(result.data["status"], "skipped")

    async def test_tool_completion_is_different_from_test_failure(self):
        self.source(
            "import unittest\nclass Sample(unittest.TestCase):\n"
            " def test_wrong(self):\n  self.assertEqual(2 + 2, 5)\n"
        )
        result = await self.execute()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["status"], "failed")
        self.assertEqual(result.data["failure_events"], 1)
        self.assertEqual(result.data["exit_code"], 1)
        self.assertIn("4 != 5", result.data["output"])

    async def test_rerun_reads_edited_source_instead_of_an_old_bytecode_cache(self):
        module = self.repo.root / "calculation.py"
        module.write_text("value = 1\n", encoding="utf-8")
        old_stat = module.stat()
        py_compile.compile(str(module), doraise=True)
        module.write_text("value = 2\n", encoding="utf-8")
        os.utime(module, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.source(
            "import unittest,calculation\nclass Sample(unittest.TestCase):\n"
            " def test_latest(self):\n  self.assertEqual(calculation.value, 2)\n"
        )
        result = await self.execute()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["status"], "passed", result.data["output"])

    async def test_zero_tests_and_all_skipped_are_not_reported_passed(self):
        self.source(
            "import unittest\n@unittest.skip('fixture skip')\n"
            "class Sample(unittest.TestCase):\n def test_skip(self):\n  pass\n"
        )
        for parameters, status in (({"pattern": "test_missing.py"}, "no_tests"), ({}, "skipped")):
            with self.subTest(status=status):
                result = await self.execute(**parameters)
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.data["status"], status)

    async def test_no_authority_denies_before_running_project_code(self):
        self.source("raise RuntimeError('MUST_NOT_RUN')\n")
        self.agent.executor.authorize = None
        result = await self.execute()
        self.assertEqual(result.error.code, "permission_denied")

    def test_already_cancelled_worker_does_not_launch_a_process(self):
        module = importlib.import_module("herta_agent.tools.coding.run_tests")
        stop = threading.Event()
        stop.set()
        started = []
        real_popen = module.subprocess.Popen

        def launch(*args, **kwargs):
            started.append(True)
            return real_popen(*args, **kwargs)

        with patch.object(module.subprocess, "Popen", side_effect=launch):
            with self.assertRaises(ToolExecutionError) as caught:
                module.run_owned(self.repo, module.TestParameters(), stop)
        self.assertEqual(started, [])
        self.assertEqual(caught.exception.code, "test_cancelled")

    def test_non_windows_execution_is_explicitly_unsupported(self):
        module = importlib.import_module("herta_agent.tools.coding.run_tests")
        self.source("import unittest\n")
        with patch.object(module.sys, "platform", "linux"):
            with self.assertRaises(ToolExecutionError) as caught:
                module.run_owned(self.repo, module.TestParameters(), threading.Event())
        self.assertEqual(caught.exception.code, "unsupported_platform")

    async def test_denied_confirmation_never_executes_test_imports(self):
        marker = self.repo.root / "must-not-exist.txt"
        self.source(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
        self.agent.executor.authorize = TerminalApproval(self.repo)
        with patch("builtins.input", return_value="no"):
            result = await self.execute()
        self.assertEqual(result.error.code, "permission_denied")
        self.assertFalse(marker.exists())

    async def test_output_limit_and_abrupt_exit_are_not_passing(self):
        self.source("print('x' * 100000)\nimport unittest\n")
        result = await self.execute()
        self.assertEqual(result.error.code, "test_output_limit")
        self.source("import os\nos._exit(0)\n")
        result = await self.execute()
        self.assertEqual(result.error.code, "test_report_invalid")

    async def test_invalid_scope_and_patterns_are_rejected(self):
        for arguments, code in (
            ({"path": "../"}, "path_denied"),
            ({"path": "missing"}, "path_missing"),
            ({"pattern": "--help"}, "invalid_arguments"),
            ({"path": "tests/test_sample.py"}, "not_directory"),
        ):
            self.source("import unittest\n")
            with self.subTest(arguments=arguments):
                result = await self.execute(**arguments)
                self.assertEqual(result.error.code, code)

    async def test_timeout_and_repeated_cancel_reap_child_tree_before_return(self):
        # The helper lives for at most five seconds even if the feature is broken.
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                heartbeat = self.repo.root / f"heartbeat-{cancel}.txt"
                ready = self.repo.root / f"ready-{cancel}.txt"
                child = (
                    "import pathlib,time; p=pathlib.Path("
                    + repr(str(heartbeat))
                    + "); end=time.monotonic()+5\nwhile time.monotonic()<end:\n"
                    " p.write_text(str(time.time_ns())); time.sleep(.02)\n"
                )
                self.source(
                    "import unittest,subprocess,sys,time,pathlib\n"
                    "class Sample(unittest.TestCase):\n"
                    " def test_wait(self):\n  subprocess.Popen([sys.executable, '-c', "
                    + repr(child)
                    + "])\n  pathlib.Path("
                    + repr(str(ready))
                    + ").write_text('ready')\n  time.sleep(5)\n"
                )
                self.agent.executor.timeout = 5 if cancel else 1.5
                task = asyncio.create_task(self.execute())
                cleanup_start = time.monotonic()
                if cancel:
                    for _ in range(150):
                        if heartbeat.exists() and ready.exists():
                            break
                        await asyncio.sleep(0.02)
                    self.assertTrue(heartbeat.exists(), "fixture child did not start")
                    cleanup_start = time.monotonic()
                    task.cancel()
                    await asyncio.sleep(0)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    result = await task
                    self.assertEqual(result.error.code, "timeout")
                self.assertTrue(heartbeat.exists(), "timeout fixture must run before cancellation")
                stopped = heartbeat.read_bytes()
                await asyncio.sleep(0.15)
                self.assertEqual(heartbeat.read_bytes(), stopped, "owned descendant kept running")
                self.assertLess(
                    time.monotonic() - cleanup_start,
                    3,
                    "cleanup waited for the fixture's five-second natural exit",
                )


@unittest.skipUnless(sys.platform == "win32", "Windows process-tree execution unit")
class TestEditLoopTests(unittest.TestCase):
    def test_actual_demo_fails_edits_and_passes_in_the_original_loop(self):
        demo = Path(__file__).resolve().parents[2] / "examples/cli-test/demo.py"
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(demo)],
            input="yes\nyes\nyes\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status=failed", result.stdout)
        self.assertIn("3 != 2", result.stdout)
        self.assertIn("status=passed", result.stdout)
        self.assertIn("return value + 1", result.stdout)
        self.assertIn("[steps=5]", result.stdout)
