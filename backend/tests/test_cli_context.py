"""CLI budget wiring and actual provider inputs, using the existing offline Read fixture."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from herta_agent.cli import create_agent, run_turn
from herta_agent.config import RunSettings
from herta_agent.llm.demo import ReadDemoProvider
from herta_agent.runtime.context_engine import ContextSettings
from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.paths import Repository


class CLIContextTests(unittest.TestCase):
    def invoke(self, root, *extra):
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
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

    def test_custom_and_default_window_reach_real_context_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "note.md").write_text("BUDGET_FIXTURE", encoding="utf-8")
            args = ("--demo-read-file", "note.md", "--trace", "--message", "读取笔记")
            default = self.invoke(root, *args)
            selected = self.invoke(root, *args, "--context-window", "8192")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertIn("/30464 Token", default.stderr)
        self.assertIn("/5888 Token", selected.stderr)
        self.assertIn("BUDGET_FIXTURE", selected.stdout)
        self.assertIn("[steps=2]", selected.stdout)

    def test_invalid_window_fails_before_provider_configuration_or_mode_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for value in ("0", "512", "2304", "2000001", "abc"):
                with self.subTest(window=value):
                    result = self.invoke(
                        root,
                        "--context-window",
                        value,
                        "--provider",
                        "openai",
                        "--message",
                        "hello",
                    )
                    self.assertIn(result.returncode, (1, 2))
                    self.assertNotIn("HERTA_API_KEY", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertNotIn("模式：", result.stdout)
                    self.assertNotIn("Assistant:", result.stdout)

    def test_current_large_request_is_rejected_before_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.invoke(
                Path(temporary), "--context-window", "8192", "--trace", "--message", "字" * 4000
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("context_budget_exceeded", result.stderr)
        self.assertNotIn("请求 Provider", result.stderr)
        self.assertNotIn("Assistant:", result.stdout)

    def test_current_large_tool_result_is_not_silently_clipped_or_answered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = "字" * 5000
            (root / "note.md").write_text(content, encoding="utf-8")
            result = self.invoke(
                root,
                "--context-window",
                "8192",
                "--trace",
                "--demo-read-file",
                "note.md",
                "--message",
                "读取这份笔记",
            )
            self.assertEqual((root / "note.md").read_text(encoding="utf-8"), content)
        self.assertEqual(result.returncode, 1)
        self.assertIn("工具 read_file 调用完成", result.stderr)
        self.assertIn("context_budget_exceeded", result.stderr)
        self.assertEqual(result.stderr.count("请求 Provider"), 1)
        self.assertNotIn("Assistant:", result.stdout)


class ContextHistoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_overflow_keeps_full_result_and_allows_a_following_short_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "note.md"
            target.write_text("字" * 5000, encoding="utf-8")
            session = Session()
            agent = create_agent(
                ReadDemoProvider("note.md"),
                RunSettings(context=ContextSettings(window_tokens=8192)),
                Repository(root),
            )
            with self.assertRaises(ContextError):
                await run_turn(agent, session, "读取大笔记")
            self.assertEqual(len(session.history), 3)
            self.assertEqual(session.history[-1].role, "tool")
            feedback = json.loads(session.history[-1].content)
            self.assertTrue(feedback["ok"])
            self.assertFalse(feedback["data"]["truncated"])
            self.assertEqual(feedback["data"]["lines"], [{"line": 1, "text": "字" * 5000}])
            target.write_text("短笔记。", encoding="utf-8")
            result = await run_turn(agent, session, "重新读取短笔记")
            self.assertEqual(result.steps, 2)
            self.assertIn("短笔记。", result.reply)
            self.assertEqual(len(session.history), 7)

    async def test_budget_selects_complete_turns_without_deleting_session_history(self):
        class RecordingReadProvider(ReadDemoProvider):
            def __init__(self):
                super().__init__("note.md")
                self.inputs = []

            async def complete(self, messages, *, tools=()):
                self.inputs.append(messages)
                return await super().complete(messages, tools=tools)

        class Sink:
            def __init__(self):
                self.diagnostics = []

            async def emit(self, event):
                if event.type == "context.prepared":
                    self.diagnostics.append(event.payload)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "note.md").write_text("演示笔记。", encoding="utf-8")
            for window, budget, expect_omission in ((8192, 5888, True), (32768, 30464, False)):
                with self.subTest(window=window):
                    provider, session, sink = RecordingReadProvider(), Session(), Sink()
                    agent = create_agent(
                        provider,
                        RunSettings(context=ContextSettings(window_tokens=window)),
                        Repository(root),
                    )
                    for number in range(1, 4):
                        result = await run_turn(
                            agent, session, f"任务{number}\n" + "背景资料" * 200, observer=sink
                        )
                        self.assertEqual(result.steps, 2)
                    self.assertEqual(len(session.history), 12)
                    self.assertTrue(session.history[0].content.startswith("任务1\n"))
                    self.assertEqual(len(provider.inputs), 6)
                    self.assertEqual(len(sink.diagnostics), 6)
                    self.assertEqual(
                        any(d["omitted_message_count"] > 0 for d in sink.diagnostics),
                        expect_omission,
                    )
                    for diagnostic in sink.diagnostics:
                        self.assertEqual(diagnostic["input_budget"], budget)
                        self.assertLessEqual(diagnostic["estimated_input_tokens"], budget)
                    for messages in provider.inputs:
                        calls = [call.id for message in messages for call in message.tool_calls]
                        results = [
                            message.tool_call_id for message in messages if message.role == "tool"
                        ]
                        self.assertEqual(calls, results)
                    tasks = [
                        m.content.splitlines()[0]
                        for m in provider.inputs[-1]
                        if m.role == "user" and m.content.startswith("任务")
                    ]
                    self.assertEqual(tasks[-1], "任务3")
                    if expect_omission:
                        self.assertLess(len(tasks), 3)
                    else:
                        self.assertEqual(tasks, ["任务1", "任务2", "任务3"])
