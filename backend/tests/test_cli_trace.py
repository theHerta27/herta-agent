"""Trace real loop/tool events without treating fixture responses as model intelligence."""

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from herta_agent.cli import create_agent, run_turn
from herta_agent.config import RunSettings
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.registry import ToolParameters, ToolRegistry, ToolSpec


class ScriptedProvider:
    def __init__(self, calls):
        self.calls = calls

    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "user":
            return ModelReply(message=Message(role="assistant", tool_calls=self.calls))
        return ModelReply(message=Message(role="assistant", content=messages[-1].content))


def read_provider():
    return ScriptedProvider(
        (ToolCall(id="read", name="read_file", arguments='{"path":"note.md"}'),)
    )


def trace(stream):
    from herta_agent.cli_events import TerminalEventSink

    return TerminalEventSink(stream)


class CLITraceTests(unittest.TestCase):
    def invoke(self, root, *extra, input_text=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("HERTA_") and key != "DEEPSEEK_API_KEY"
        }
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        return subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-m", "herta_agent", "--repo", str(root), *extra],
            cwd=root,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

    def test_explicit_trace_shows_read_progress_on_stderr_without_dumping_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "note.md").write_text("FILE_BODY_FIXTURE", encoding="utf-8")
            args = ("--demo-read-file", "note.md", "--message", "USER_INPUT_FIXTURE")
            plain = self.invoke(root, *args)
            observed = self.invoke(root, *args, "--trace")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(plain.stderr, "")
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertIn("[steps=2]", observed.stdout)
        self.assertIn("FILE_BODY_FIXTURE", observed.stdout)
        self.assertNotIn("FILE_BODY_FIXTURE", observed.stderr)
        self.assertNotIn("USER_INPUT_FIXTURE", observed.stderr)
        expected = [
            "[步骤1] 上下文",
            "[步骤1] 请求 Provider",
            "[步骤1] 开始工具 read_file",
            "[步骤1] 工具 read_file 调用完成",
            "[步骤2] 上下文",
            "[步骤2] 请求 Provider",
        ]
        positions = [observed.stderr.index(part) for part in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("估算", observed.stderr)

    def test_interactive_trace_restarts_step_numbers_for_each_user_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.invoke(Path(temporary), "--trace", input_text="第一轮\n第二轮\n/exit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("[步骤1] 请求 Provider"), 2)
        self.assertNotIn("[步骤2]", result.stderr)
        self.assertIn("第 2 轮", result.stdout)


class TraceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "note.md").write_text("FILE_BODY_FIXTURE", encoding="utf-8")
        self.repo = Repository(self.root)

    async def test_observer_does_not_change_reply_or_add_events_to_session_history(self):
        plain, observed = Session(), Session()
        plain_result = await run_turn(
            create_agent(read_provider(), RunSettings(), self.repo), plain, "读"
        )
        stream = io.StringIO()
        traced_result = await run_turn(
            create_agent(read_provider(), RunSettings(), self.repo),
            observed,
            "读",
            observer=trace(stream),
        )
        self.assertEqual(traced_result.reply, plain_result.reply)
        self.assertEqual(traced_result.context_hash, plain_result.context_hash)
        self.assertEqual(observed.history, plain.history)
        self.assertEqual(len(observed.history), 4)
        self.assertNotIn("FILE_BODY_FIXTURE", stream.getvalue())

    async def test_rejected_calls_never_claim_to_have_started_or_completed(self):
        calls = (
            ToolCall(id="invalid", name="read_file", arguments='{"path":"note.md","start_line":0}'),
            ToolCall(id="unknown", name="missing_tool", arguments="{}"),
            ToolCall(id="denied", name="edit_file", arguments="{}"),
        )
        stream = io.StringIO()
        result = await run_turn(
            create_agent(ScriptedProvider(calls), RunSettings(), self.repo),
            Session(),
            "go",
            observer=trace(stream),
        )
        output = stream.getvalue()
        for code in ("invalid_arguments", "unknown_tool", "permission_denied"):
            self.assertIn(code, output)
        self.assertNotIn("开始工具", output)
        self.assertNotIn("调用完成", output)
        self.assertFalse(json.loads(result.reply)["ok"])
        self.assertEqual((self.root / "note.md").read_text(encoding="utf-8"), "FILE_BODY_FIXTURE")

    async def test_real_tool_error_has_a_failed_event_and_single_line_escaped_code(self):
        async def fail(parameters):
            raise ToolExecutionError("bad\x1b[31m\n\t\u202e" + "x" * 1000, "ERROR_BODY_FIXTURE")

        registry = ToolRegistry()
        registry.register(ToolSpec("fail", "fixture", ToolParameters, fail))
        agent = Agent(
            ScriptedProvider((ToolCall(id="fail", name="fail", arguments="{}"),)), registry=registry
        )
        stream = io.StringIO()
        await run_turn(agent, Session(), "USER_INPUT_FIXTURE", observer=trace(stream))
        output = stream.getvalue()
        lines = [line for line in output.splitlines() if "工具 fail" in line]
        self.assertEqual(len(lines), 2)
        self.assertIn("未完成", lines[-1])
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\u202e", output)
        self.assertNotIn("\t", output)
        self.assertLess(len(lines[-1]), 1000)
        self.assertNotIn("ERROR_BODY_FIXTURE", output)
        self.assertNotIn("调用完成", output)

    async def test_broken_trace_stream_does_not_abort_real_tool_or_answer(self):
        class BrokenStream:
            def write(self, text):
                raise BrokenPipeError("closed trace output")

            def flush(self):
                pass

        result = await run_turn(
            create_agent(read_provider(), RunSettings(), self.repo),
            Session(),
            "读",
            observer=trace(BrokenStream()),
        )
        self.assertTrue(json.loads(result.reply)["ok"])
        self.assertEqual(result.steps, 2)

    @unittest.skipUnless(sys.platform == "win32", "run_tests is Windows-only")
    async def test_failed_test_suite_is_displayed_as_a_completed_call_with_failed_status(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/test_demo.py").write_text(
            "import unittest\nclass Demo(unittest.TestCase):\n"
            "    def test_failure(self):\n        self.assertEqual(3, 2)\n",
            encoding="utf-8",
        )

        async def allow_this_fixture(spec, parameters):
            return True

        provider = ScriptedProvider((ToolCall(id="test", name="run_tests", arguments="{}"),))
        stream = io.StringIO()
        result = await run_turn(
            create_agent(provider, RunSettings(), self.repo, authorize=allow_this_fixture),
            Session(),
            "测试",
            observer=trace(stream),
        )
        feedback = json.loads(result.reply)
        self.assertTrue(feedback["ok"])
        self.assertEqual(feedback["data"]["status"], "failed")
        self.assertIn("工具 run_tests 调用完成；测试状态=failed", stream.getvalue())
        self.assertNotIn("3 != 2", stream.getvalue())

    async def test_cancellation_does_not_print_a_tool_completion(self):
        started = asyncio.Event()

        async def wait(parameters):
            started.set()
            await asyncio.sleep(30)

        registry = ToolRegistry()
        registry.register(ToolSpec("wait", "fixture", ToolParameters, wait))
        agent = Agent(
            ScriptedProvider((ToolCall(id="wait", name="wait", arguments="{}"),)), registry=registry
        )
        stream, session = io.StringIO(), Session()
        task = asyncio.create_task(run_turn(agent, session, "等待", observer=trace(stream)))
        try:
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertNotIn("调用完成", stream.getvalue())
        self.assertIn('"cancelled"', session.history[-1].content)


if __name__ == "__main__":
    unittest.main()
