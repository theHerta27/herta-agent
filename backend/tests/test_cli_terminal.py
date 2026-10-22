"""Real terminal rendering, keyboard handling and approvals; no network or model calls."""

import asyncio
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from herta_agent.cli import create_agent, print_result, run_turn
from herta_agent.config import RunSettings
from herta_agent.runtime.events import RuntimeEvent
from herta_agent.runtime.messages import Message, ModelReply, RunResult, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.edit_file import EditParameters, prepare_edit
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    def ui(self, pipe=None, width=86, trace=None):
        self.assertIsNotNone(
            importlib.util.find_spec("herta_agent.terminal_ui"),
            "The terminal presentation layer is not implemented yet",
        )
        from herta_agent.terminal_ui import TerminalUI

        stream = io.StringIO()
        console = Console(file=stream, width=width, color_system=None)
        return TerminalUI(console=console, input=pipe, output=DummyOutput(), trace=trace), stream

    def test_welcome_is_readable_without_internal_identifiers(self):
        ui, stream = self.ui()
        ui.welcome(Path("demo-project"), "deepseek-flash", demo=False)
        ui.session_info("a" * 32, Path("sensitive-state/sessions.sqlite3"))
        text = stream.getvalue()
        for value in ("Herta Agent", "demo-project", "deepseek-flash", "/exit"):
            self.assertIn(value, text)
        self.assertNotIn("a" * 32, text)
        self.assertNotIn("sessions.sqlite3", text)

    def test_markdown_is_rendered_and_control_characters_are_not_executed(self):
        ui, stream = self.ui()
        ui.answer("## 修复结果\n\n**已完成**\n\n```python\nreturn 0\n```\n\x1b[2J")
        text = stream.getvalue()
        self.assertIn("修复结果", text)
        self.assertIn("return 0", text)
        self.assertNotIn("## 修复结果", text)
        self.assertNotIn("```", text)
        self.assertNotIn("\x1b", text)

    def test_trace_adds_metadata_without_printing_the_answer_twice(self):
        ui, display = self.ui(trace=object())
        raw = io.StringIO()
        result = RunResult(session_id="s", reply="ANSWER_BODY", steps=1, context_hash="a" * 64)
        with redirect_stdout(raw):
            print_result(result, terminal=ui)
        self.assertEqual(display.getvalue().count("ANSWER_BODY"), 1)
        self.assertNotIn("ANSWER_BODY", raw.getvalue())
        self.assertIn("[steps=1]", raw.getvalue())

    def test_diff_keeps_actual_added_deleted_text_and_escapes_controls(self):
        ui, stream = self.ui(width=48)
        ui.preview_change(
            "note[red].py",
            "--- a/note.py\r\n+++ b/note.py\r\n-value = 1\r\n+value = 2\r\n+\x1b[2J\n",
        )
        text = stream.getvalue()
        for value in ("note[red].py", "-value = 1", "+value = 2", "尚未写入"):
            self.assertIn(value, text)
        self.assertNotIn("\x1b", text)
        self.assertIn("\\r", text)

    def test_newline_only_edit_displays_which_side_has_carriage_return(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder))
            for before, old, new, marked in (
                (b"value = 1\r\n", "\r\n", "\n", "-value = 1\\r"),
                (b"value = 1\n", "\n", "\r\n", "+value = 1\\r"),
            ):
                with self.subTest(before=before):
                    (repo.root / "note.py").write_bytes(before)
                    change = prepare_edit(
                        repo,
                        EditParameters(
                            path="note.py",
                            expected_sha256=hashlib.sha256(before).hexdigest(),
                            old_text=old,
                            new_text=new,
                        ),
                    )
                    ui, stream = self.ui()
                    ui.preview_change("note.py", change.diff)
                    self.assertIn(marked, stream.getvalue())
                    self.assertEqual((repo.root / "note.py").read_bytes(), before)

    async def test_dumb_prompt_string_requires_the_complete_yes_word(self):
        for answer, allowed in (
            ("yes", True),
            (" YES ", True),
            ("y", False),
            ("", False),
            ("yes\nno", False),
        ):
            with (
                self.subTest(answer=answer),
                patch("herta_agent.terminal_ui.PromptSession") as prompt,
            ):
                prompt.return_value.prompt_async = AsyncMock(return_value=answer)
                ui, _ = self.ui()
                self.assertIs(await ui.confirm(), allowed)

    async def test_progress_uses_verified_result_paths_and_distinguishes_test_failure(self):
        ui, stream = self.ui()
        await ui.emit(
            RuntimeEvent(
                type="context.prepared",
                step=1,
                message_id="c",
                payload={"estimated_input_tokens": 1234},
            )
        )
        await ui.emit(
            RuntimeEvent(type="tool.started", step=1, message_id="r", payload={"name": "read_file"})
        )
        await ui.emit(
            RuntimeEvent(
                type="tool.completed",
                step=1,
                message_id="r",
                payload={
                    "name": "read_file",
                    "result": {
                        "ok": True,
                        "data": {
                            "path": "metrics.py",
                            "lines": [{"text": "FILE_BODY_MUST_NOT_LEAK"}],
                        },
                    },
                },
            )
        )
        await ui.emit(
            RuntimeEvent(
                type="tool.completed",
                step=2,
                message_id="t",
                payload={
                    "name": "run_tests",
                    "result": {
                        "ok": True,
                        "data": {
                            "status": "failed",
                            "tests_run": 3,
                            "successful_tests": 2,
                            "output": "PRIVATE_TEST_BODY",
                        },
                    },
                },
            )
        )
        text = stream.getvalue()
        self.assertIn("已读取 metrics.py", text)
        self.assertIn("测试未通过", text)
        for value in ("1234", "FILE_BODY_MUST_NOT_LEAK", "PRIVATE_TEST_BODY", "调用完成"):
            self.assertNotIn(value, text)

    async def test_denied_action_does_not_look_like_a_success(self):
        ui, stream = self.ui()
        await ui.emit(
            RuntimeEvent(
                type="tool.failed",
                step=1,
                message_id="d",
                payload={
                    "name": "edit_file",
                    "result": {
                        "ok": False,
                        "error": {"code": "permission_denied", "message": "not approved"},
                    },
                },
            )
        )
        self.assertIn("未获确认", stream.getvalue())
        self.assertNotIn("已修改", stream.getvalue())

    async def test_default_enter_declines_and_right_enter_explicitly_approves(self):
        for keys, expected in (
            ("yes\r", True),
            ("no\r", False),
            ("y\r", False),
            ("\r", False),
            ("\x1b[C\r", True),
            ("\x03", False),
            ("\x04", False),
        ):
            with self.subTest(keys=repr(keys)), create_pipe_input() as pipe:
                ui, _ = self.ui(pipe)
                pipe.send_text(keys)
                self.assertIs(await asyncio.wait_for(ui.confirm(), 3), expected)

    async def test_test_command_details_never_grant_approval(self):
        with create_pipe_input() as pipe:
            ui, stream = self.ui(pipe)
            ui.preview_test(Path("demo"), ["python.exe", "-I", "worker.py", "demo/tests"])
            pipe.send_text("d\r")
            self.assertFalse(await asyncio.wait_for(ui.confirm(), 3))
            self.assertIn("worker.py", stream.getvalue())
            self.assertIn("当前账号权限", stream.getvalue())

    async def test_multiline_paste_and_history_are_real_prompt_input(self):
        with create_pipe_input() as pipe:
            ui, _ = self.ui(pipe)
            pipe.send_text("\x1b[200~第一行\n第二行\x1b[201~\r")
            self.assertEqual(await asyncio.wait_for(ui.read_async(), 3), "第一行\n第二行")
            next_prompt = asyncio.create_task(ui.read_async())
            # History is loaded asynchronously; press Up once the prompt is displayed.
            await asyncio.sleep(0.05)
            pipe.send_text("\x1b[A\r")
            self.assertEqual(await asyncio.wait_for(next_prompt, 3), "第一行\n第二行")

    async def test_spinner_stops_on_model_completion_and_explicit_cleanup(self):
        ui, _ = self.ui()
        await ui.emit(RuntimeEvent(type="llm.started", step=1, message_id="m"))
        self.assertIsNotNone(ui.waiting)
        await ui.emit(RuntimeEvent(type="llm.completed", step=1, message_id="m"))
        self.assertIsNone(ui.waiting)
        ui.stop_wait()

    async def test_keyboard_approval_uses_existing_executor_and_real_file_checks(self):
        for keys, written in (("\r", False), ("\x1b[C\r", True)):
            with (
                self.subTest(written=written),
                tempfile.TemporaryDirectory() as folder,
                create_pipe_input() as pipe,
            ):
                root = Path(folder)
                target = root / "note.py"
                target.write_text("value = 1\n", encoding="utf-8")
                ui, stream = self.ui(pipe)
                pipe.send_text(keys)

                class Provider:
                    async def complete(self, messages, *, tools=()):
                        if messages[-1].role == "user":
                            call = ToolCall(
                                id="read", name="read_file", arguments='{"path":"note.py"}'
                            )
                        elif messages[-1].tool_call_id == "read":
                            data = json.loads(messages[-1].content)["data"]
                            call = ToolCall(
                                id="edit",
                                name="edit_file",
                                arguments=json.dumps(
                                    {
                                        "path": "note.py",
                                        "expected_sha256": data["sha256"],
                                        "old_text": "value = 1",
                                        "new_text": "value = 2",
                                    }
                                ),
                            )
                        else:
                            return ModelReply(
                                message=Message(role="assistant", content=messages[-1].content)
                            )
                        return ModelReply(message=Message(role="assistant", tool_calls=(call,)))

                repo = Repository(root)
                agent = create_agent(
                    Provider(), RunSettings(), repo, authorize=TerminalApproval(repo, presenter=ui)
                )
                result = await run_turn(agent, Session(), "edit", observer=ui)
                self.assertEqual(
                    target.read_text(encoding="utf-8"), "value = 2\n" if written else "value = 1\n"
                )
                self.assertEqual(json.loads(result.reply)["ok"], written)
                self.assertIn("尚未写入", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
