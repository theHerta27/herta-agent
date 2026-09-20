import asyncio
import hashlib
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from herta_agent.persona import PersonaContextBuilder
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.context import ContextSnapshot, StaticContextBuilder
from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import EchoParameters, echo_registry
from herta_agent.tools.registry import ToolSpec


class ContextTests(unittest.TestCase):
    def test_full_text_bom_crlf_and_frozen_snapshot(self):
        text = "# 人格\r\n\r\n完整正文 **保留**。\r\n尾部\r\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "中文 soul.md"
            path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            snapshot = PersonaContextBuilder(path).snapshot()
        self.assertEqual(snapshot.system_text, text)
        self.assertEqual(snapshot.sha256, hashlib.sha256(text.encode("utf-8")).hexdigest())
        with self.assertRaises(FrozenInstanceError):
            snapshot.system_text = "changed"

    def test_build_keeps_history_and_tool_ids_without_mutation(self):
        history = (
            Message(role="user", content="question"),
            Message(role="assistant", tool_calls=(ToolCall(id="a", name="echo", arguments="{}"),)),
            Message(role="tool", tool_call_id="a", content='{"ok":true}'),
        )
        context = ContextSnapshot("persona")
        messages = context.build_messages(history)
        self.assertEqual(messages[0], Message(role="system", content="persona"))
        self.assertEqual(messages[1:], history)
        self.assertIs(messages[-1], history[-1])
        with self.assertRaises(ContextError):
            context.build_messages((Message(role="system", content="duplicate"),))

    def test_bad_files_raise_clear_context_error_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soul.md"
            builder = PersonaContextBuilder(path)
            with self.assertRaisesRegex(ContextError, "读取"):
                builder.snapshot()
            for body in [b"", b" \r\n", b"\xff", b"text\x00"]:
                path.write_bytes(body)
                with self.subTest(body=body), self.assertRaises(ContextError):
                    builder.snapshot()
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                with self.assertRaisesRegex(ContextError, "读取"):
                    builder.snapshot()
            with self.assertRaises(ContextError):
                PersonaContextBuilder(Path(directory)).snapshot()


class ContextRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_stable_during_tool_then_next_run_reloads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soul.md"
            path.write_text("original 全文\n", encoding="utf-8")
            original = path.read_bytes().decode("utf-8")
            requests = []

            async def edit(args):
                path.write_text("updated 全文\n", encoding="utf-8")
                return {"edited": True}

            class Provider:
                async def complete(self, messages, *, tools=()):
                    requests.append(messages)
                    if len(requests) == 1:
                        return ModelReply(
                            message=Message(
                                role="assistant",
                                tool_calls=(
                                    ToolCall(id="edit", name="edit", arguments='{"text":"x"}'),
                                ),
                            )
                        )
                    return ModelReply(message=Message(role="assistant", content="answer"))

            registry = echo_registry()
            registry.register(ToolSpec("edit", "Edit fixture", EchoParameters, edit))
            agent = Agent(
                Provider(), registry=registry, context_builder=PersonaContextBuilder(path)
            )
            session = Session()
            first = await agent.run(session, "first")
            second = await agent.run(session, "second")
        self.assertEqual([r[0].content for r in requests[:2]], [original, original])
        self.assertIn("updated", requests[2][0].content)
        self.assertNotEqual(first.context_hash, second.context_hash)
        self.assertEqual(session.context_hash, second.context_hash)
        self.assertEqual(first.context_hash, hashlib.sha256(original.encode()).hexdigest())
        self.assertTrue(all(sum(m.role == "system" for m in r) == 1 for r in requests))
        self.assertNotIn("system", [m.role for m in session.history])

    async def test_failure_preserves_session_no_provider_call_then_repair(self):
        requests = []

        class Provider:
            async def complete(self, messages, *, tools=()):
                requests.append(messages)
                return ModelReply(message=Message(role="assistant", content="answer"))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soul.md"
            agent = Agent(Provider(), context_builder=PersonaContextBuilder(path))
            session = Session()
            path.write_text("valid", encoding="utf-8")
            await agent.run(session, "first")
            for body in [b"", b" \n", b"\xff", b"bad\x00"]:
                path.write_bytes(body)
                with self.assertRaises(ContextError):
                    await agent.run(session, "failed")
                self.assertIsNone(session.context_hash)
                self.assertEqual(len(requests), 1)
            path.unlink()
            with self.assertRaises(ContextError):
                await agent.run(session, "missing")
            path.write_text("repaired", encoding="utf-8")
            result = await agent.run(session, "retry")
        self.assertEqual(result.session_id, session.session_id)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[-1][0].content, "repaired")
        self.assertEqual(
            [m.content for m in session.history if m.role == "user"],
            ["first", *["failed"] * 4, "missing", "retry"],
        )

    async def test_builder_injection_loads_once_and_cancel_releases_session(self):
        started = asyncio.Event()

        class Builder:
            calls = 0

            def snapshot(self):
                self.calls += 1
                return ContextSnapshot("custom without persona file")

        class Waiting:
            async def complete(self, messages, *, tools=()):
                started.set()
                await asyncio.Event().wait()

        builder, session = Builder(), Session()
        task = asyncio.create_task(Agent(Waiting(), context_builder=builder).run(session, "cancel"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(builder.calls, 1)
        self.assertEqual(
            session.context_hash, ContextSnapshot("custom without persona file").sha256
        )
        from herta_agent.llm.demo import DemoProvider

        result = await Agent(DemoProvider(), context_builder=StaticContextBuilder("other")).run(
            session, "retry"
        )
        self.assertEqual(result.context_hash, ContextSnapshot("other").sha256)
