"""Real Docker only. Never replace Docker with a stub in this module."""

import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.run_tests import run_tests
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


@unittest.skipUnless(os.environ.get("HERTA_DOCKER_TESTS") == "1", "requires real Docker + image")
class DockerSandboxIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "tests").mkdir()
        (root / "tests/test_probe.py").write_text("", encoding="utf-8")
        self.workspace = Workspace.open(root)

    async def execute(self, code, deadline=30):
        (self.workspace.root / "tests/test_probe.py").write_text(code, encoding="utf-8")
        registry = ToolRegistry()
        registry.register(run_tests(self.workspace, timeout=deadline))
        return await ToolExecutor(registry).execute(
            ToolCall(id="sandbox-integration", name="run_tests", arguments="{}")
        )

    async def test_network_denied_nonroot_and_system_write_denied(self):
        result = await self.execute(
            "import os,socket,unittest\nclass Probe(unittest.TestCase):\n"
            "    def test_network(self):\n"
            '        with self.assertRaises(OSError): socket.create_connection(("1.1.1.1",443),1)\n'
            "    def test_nonroot(self): self.assertNotEqual(os.getuid(),0)\n"
            "    def test_system_write(self):\n"
            '        with self.assertRaises(OSError): open("/etc/herta-write-probe","w")\n'
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["status"], "passed")
        self.assertEqual(result.data["passed"], 3)

    async def test_timeout_and_cancellation_remove_exact_container(self):
        from herta_agent.tools.coding.sandbox import container_name

        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                name = container_name()
                from unittest.mock import patch

                with patch("herta_agent.tools.coding.run_tests.container_name", return_value=name):
                    task = asyncio.create_task(
                        self.execute(
                            "import time\nfrom pathlib import Path\n"
                            'Path("ready").touch()\ntime.sleep(120)\n',
                            deadline=8,
                        )
                    )
                    if cancel:
                        async with asyncio.timeout(6):
                            while not (self.workspace.root / "ready").exists():  # noqa: ASYNC110
                                await asyncio.sleep(0.05)
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        result = await task
                        self.assertEqual(result.error.code, "timeout")
                        self.assertTrue((self.workspace.root / "ready").exists())
                completed = await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                self.assertEqual(completed.stdout.strip(), "")
                (self.workspace.root / "ready").unlink(missing_ok=True)

    async def test_failed_then_passed_results_and_subtests(self):
        failed = await self.execute(
            "import unittest\nclass Probe(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        for i in (1,2):\n"
            "            with self.subTest(i=i): self.assertEqual(i,0)\n"
            "    def test_skip(self):\n"
            "        for i in (1,2):\n"
            '            with self.subTest(i=i): self.skipTest("sub")\n'
        )
        self.assertTrue(failed.ok, failed.error)
        self.assertEqual(
            [failed.data[k] for k in ("total", "passed", "failed", "skipped", "skipped_subtests")],
            [2, 1, 1, 0, 2],
        )
        self.assertEqual(len(failed.data["tests"][0]["subtests"]), 2)
        passed = await self.execute(
            "import unittest\nclass Probe(unittest.TestCase):\n"
            "    def test_ok(self): self.assertEqual(2,2)\n"
        )
        self.assertTrue(passed.ok, passed.error)
        self.assertEqual(passed.data["status"], "passed")
        self.assertEqual(passed.data["passed"], 1)
