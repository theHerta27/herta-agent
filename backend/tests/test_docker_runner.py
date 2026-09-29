import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.run_tests import run_tests
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class DockerRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_during_cleanup_keeps_workspace_owned_until_reaped(self):
        import sys

        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace.open(Path(folder))
            (workspace.root / "tests").mkdir()
            cleanup_started, release_cleanup = asyncio.Event(), asyncio.Event()
            cleaned = False

            async def cleanup(docker, name, process):
                nonlocal cleaned
                cleanup_started.set()
                await release_cleanup.wait()
                await process.wait()
                cleaned = True

            def command(docker, name, ws, path, pattern, report, image):
                data = {
                    "exitcode": 0,
                    "summary": {"total": 1, "passed": 1},
                    "tests": [{"nodeid": "one", "outcome": "passed"}],
                }
                return [
                    sys.executable,
                    "-c",
                    "import sys; from pathlib import Path; "
                    'Path(sys.argv[1]).write_text(sys.argv[2],encoding="utf-8")',
                    str(ws.root / report),
                    json.dumps(data),
                ]

            registry = ToolRegistry()
            registry.register(run_tests(workspace))
            with (
                patch(
                    "herta_agent.tools.coding.run_tests.check_docker",
                    return_value=("docker", "image"),
                ),
                patch("herta_agent.tools.coding.run_tests.docker_command", side_effect=command),
                patch("herta_agent.tools.coding.run_tests.cleanup_container", side_effect=cleanup),
            ):
                task = asyncio.create_task(
                    ToolExecutor(registry).execute(
                        ToolCall(id="cleanup-cancel", name="run_tests", arguments="{}")
                    )
                )
                try:
                    await asyncio.wait_for(cleanup_started.wait(), 3)
                    task.cancel()
                    await asyncio.sleep(0.02)
                    self.assertFalse(
                        task.done(), "cleanup must retain ownership after cancellation"
                    )
                    self.assertTrue(workspace.lock.locked())
                    task.cancel()  # A second Stop must not abandon the owned cleanup either.
                    await asyncio.sleep(0.02)
                    self.assertFalse(task.done())
                finally:
                    release_cleanup.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
            self.assertTrue(cleaned)
            self.assertFalse(workspace.lock.locked())

    async def test_service_checks_docker_at_startup_without_disabling_chat(self):
        import httpx

        from herta_agent.service.app import create_app
        from herta_agent.service.settings import ServiceSettings

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch.dict(
                    "os.environ",
                    {"HERTA_CODING_REPO_ROOT": str(root), "HERTA_CODING_MODE": "coding"},
                ),
                patch("shutil.which", return_value=None),
            ):
                app = create_app(ServiceSettings(db_path=root / "db.sqlite", provider="demo"))
                async with app.router.lifespan_context(app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://local"
                    ) as client:
                        health = (await client.get("/health")).json()
                self.assertTrue(health["chat_available"])
                self.assertFalse(health["test_runner_available"])
                self.assertEqual(health["test_runner_error"], "docker_unavailable")

    async def test_missing_docker_rejects_without_local_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            (source / "tests").mkdir()
            (source / "tests/test_marker.py").write_text(
                'from pathlib import Path\nPath("executed").touch()\n', encoding="utf-8"
            )
            workspace = Workspace.open(source)
            registry = ToolRegistry()
            registry.register(run_tests(workspace))
            with patch("shutil.which", return_value=None):
                result = await ToolExecutor(registry).execute(
                    ToolCall(id="no-docker", name="run_tests", arguments="{}")
                )
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "docker_unavailable")
            self.assertFalse((workspace.root / "executed").exists())

    async def test_unique_container_identity_tracks_tool_call(self):
        from herta_agent.tools.coding.sandbox import container_name

        observed = []

        async def handler(params):
            observed.append(container_name())
            await asyncio.sleep(0)
            observed.append(container_name())

        from herta_agent.tools.coding.run_tests import TestParameters
        from herta_agent.tools.registry import ToolSpec

        registry = ToolRegistry()
        registry.register(ToolSpec("identity", "identity probe", TestParameters, handler))
        await ToolExecutor(registry).execute(
            ToolCall(id="call/a:1", name="identity", arguments=json.dumps({}))
        )
        self.assertNotEqual(observed[0], observed[1])
        self.assertEqual(observed[0].split("-")[1], observed[1].split("-")[1])
        self.assertNotEqual(observed[0].split("-")[1], container_name().split("-")[1])

    def test_command_mounts_only_workspace_with_required_restrictions(self):
        from herta_agent.tools.coding.sandbox import docker_command

        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace.open(Path(folder))
            command = docker_command(
                "docker",
                "herta-test-name",
                workspace,
                ".",
                "test*.py",
                ".coding-test-result.json",
                "herta-coding-sandbox:local",
            )
            self.assertIn("--rm", command)
            for flag, value in (
                ("--network", "none"),
                ("--user", "10001:10001"),
                ("--memory", "1g"),
                ("--cpus", "2"),
                ("--pids-limit", "128"),
            ):
                self.assertEqual(command[command.index(flag) + 1], value)
            mounts = [command[i + 1] for i, value in enumerate(command) if value == "--mount"]
            self.assertEqual(mounts, [f"type=bind,source={workspace.root},target=/workspace"])
            self.assertNotIn("/var/run/docker.sock", " ".join(command))
            self.assertNotIn("--privileged", command)
