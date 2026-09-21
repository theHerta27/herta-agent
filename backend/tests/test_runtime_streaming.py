"""Controllable synthetic deltas exercise the real single Loop and persistent Store."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import httpx
from test_provider_streaming import DONE, Bytes, frame

from herta_agent.config import ProviderSettings, RunSettings
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.persona import PersonaContextBuilder
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.context import StaticContextBuilder
from herta_agent.runtime.errors import (
    AgentError,
    ProviderProtocolError,
    StepLimitExceeded,
    ToolCallLimitExceeded,
)
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.service.runs import RunManager
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.tools.echo import echo_registry
from herta_agent.tools.registry import ToolRegistry
from herta_agent.tools.search_knowledge import search_knowledge_spec


def reply(content="done", calls=()):
    return ReplyCompleted(
        ModelReply(message=Message(role="assistant", content=content, tool_calls=calls))
    )


class Sink:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


class RuntimeStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_stream_rag_tool_and_persona_snapshot_together(self):
        class Retriever:
            async def search(self, query):
                return {"query": query, "chunks": [{"id": "fixture-1", "text": "离线证据"}]}

        registry = ToolRegistry()
        registry.register(search_knowledge_spec(Retriever()))
        bodies = []
        with tempfile.TemporaryDirectory() as directory:
            soul = Path(directory) / "soul.md"
            soul.write_text("本轮人格快照", encoding="utf-8")

            def handle(request):
                bodies.append(json.loads(request.content))
                if len(bodies) == 1:
                    soul.write_text("下轮才生效", encoding="utf-8")
                    wire = frame(
                        {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "search",
                                    "type": "function",
                                    "function": {
                                        "name": "search_knowledge",
                                        "arguments": '{"query":"黑塔"}',
                                    },
                                }
                            ]
                        }
                    )
                    wire += frame(finish="tool_calls") + DONE
                else:
                    result = json.loads(bodies[-1]["messages"][-1]["content"])
                    self.assertEqual(result["data"]["chunks"][0]["id"], "fixture-1")
                    wire = frame({"content": "依据"}) + frame({"content": "[fixture-1]"})
                    wire += frame(finish="stop") + DONE
                return httpx.Response(
                    200, stream=Bytes([wire[i : i + 2] for i in range(0, len(wire), 2)])
                )

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                provider = OpenAICompatibleProvider(
                    ProviderSettings(
                        base_url="https://fixture.test/v1", model="fixture", api_key=uuid4().hex
                    ),
                    client,
                )
                sink = Sink()
                result = await Agent(
                    provider,
                    registry=registry,
                    context_builder=PersonaContextBuilder(soul),
                    streaming=True,
                ).run(Session(), "黑塔是谁", observer=sink)
            self.assertEqual(result.steps, 2)
            self.assertEqual(result.reply, "依据[fixture-1]")
            self.assertTrue(all(b["stream"] for b in bodies))
            self.assertTrue(all(b["messages"][0]["content"] == "本轮人格快照" for b in bodies))

    async def test_one_loop_tools_and_context_snapshot_with_transient_deltas(self):
        class Context:
            calls = 0

            def snapshot(self):
                self.calls += 1
                return StaticContextBuilder().snapshot()

        class Provider:
            def __init__(self):
                self.requests = []
                self.closed = 0

            async def stream(self, messages, *, tools=()):
                self.requests.append(messages)
                try:
                    yield TextDelta("临时展示")
                    if len(self.requests) == 1:
                        yield reply(
                            None, (ToolCall(id="a", name="echo", arguments='{"text":"知识结果"}'),)
                        )
                    else:
                        yield reply("完整回答")
                finally:
                    self.closed += 1

        context, provider, sink, session = Context(), Provider(), Sink(), Session()
        result = await Agent(
            provider, registry=echo_registry(), context_builder=context, streaming=True
        ).run(session, "go", observer=sink)
        self.assertEqual(result.reply, "完整回答")
        self.assertEqual(context.calls, 1)
        self.assertEqual(provider.closed, 2)
        self.assertEqual(provider.requests[0][0], provider.requests[1][0])
        self.assertEqual(
            [m.role for m in session.history], ["user", "assistant", "tool", "assistant"]
        )
        self.assertEqual(json.loads(provider.requests[1][-1].content)["data"], {"text": "知识结果"})
        self.assertFalse(any(m.content == "临时展示" for m in session.history))
        deltas = [e for e in sink.events if e.type == "llm.delta"]
        ends = [e for e in sink.events if e.type == "llm.completed"]
        self.assertEqual([e.message_id for e in deltas], [e.message_id for e in ends])

    async def test_requires_explicit_supported_streaming_provider(self):
        class OnlyComplete:
            async def complete(self, messages, *, tools=()):
                return ModelReply(message=Message(role="assistant", content="complete"))

        with self.assertRaises(AgentError):
            Agent(OnlyComplete(), streaming=True)
        self.assertEqual((await Agent(OnlyComplete()).run(Session(), "go")).reply, "complete")

    async def test_protocol_accepts_async_iterator_without_optional_aclose(self):
        class Events:
            def __init__(self):
                self.events = iter([TextDelta("done"), reply()])

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.events)
                except StopIteration:
                    raise StopAsyncIteration from None

        class Provider:
            def stream(self, messages, *, tools=()):
                return Events()

        result = await Agent(Provider(), streaming=True).run(Session(), "go")
        self.assertEqual(result.reply, "done")

    async def test_missing_duplicate_or_late_stream_events_do_not_commit(self):
        for events in (
            [TextDelta("partial")],
            [reply(), reply()],
            [reply(), TextDelta("late")],
            [object()],
        ):

            class Provider:
                async def stream(self, messages, *, tools=(), sequence=events):
                    for event in sequence:
                        yield event

            session = Session()
            with self.assertRaises(ProviderProtocolError):
                await Agent(Provider(), streaming=True).run(session, "go")
            self.assertEqual(len(session.history), 1)

    async def test_streaming_budget_and_tool_errors_use_existing_loop(self):
        for count, max_steps, expected in (
            (1, 1, StepLimitExceeded),
            (5, 8, ToolCallLimitExceeded),
        ):

            class Provider:
                async def stream(self, messages, *, tools=(), n=count):
                    yield reply(
                        None,
                        tuple(ToolCall(id=str(i), name="echo", arguments="{") for i in range(n)),
                    )

            session = Session()
            with self.assertRaises(expected):
                await Agent(
                    Provider(),
                    RunSettings(max_steps=max_steps),
                    registry=echo_registry(),
                    streaming=True,
                ).run(session, "go")
            self.assertEqual(len([m for m in session.history if m.role == "tool"]), count)

        class Errors:
            count = 0

            async def stream(self, messages, *, tools=()):
                self.count += 1
                if self.count == 1:
                    yield reply(None, (ToolCall(id="a", name="echo", arguments="{"),))
                else:
                    yield reply(messages[-1].content)

        result = await Agent(Errors(), registry=echo_registry(), streaming=True).run(
            Session(), "go"
        )
        self.assertEqual(json.loads(result.reply)["error"]["code"], "invalid_arguments")

    async def test_partial_isolation_across_cancel_timeout_protocol_and_commit_failure(self):
        for mode in ("cancel", "timeout", "protocol", "commit"):
            await self._isolation_case(mode)

    async def _isolation_case(self, mode):
        entered, closed = asyncio.Event(), asyncio.Event()

        class Provider:
            async def stream(self, messages, *, tools=()):
                try:
                    yield TextDelta("不得保存的半截文本")
                    entered.set()
                    if mode in ("cancel", "timeout"):
                        await asyncio.Event().wait()
                    if mode == "protocol":
                        raise ProviderProtocolError("invalid finish")
                    yield reply("不得保存的半截文本")
                finally:
                    closed.set()

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteSessionStore(Path(directory) / "上下文.sqlite3")
            await store.open()
            try:
                sid = (await store.create_session()).session_id
                if mode == "commit":
                    connection = sqlite3.connect(store.path)
                    try:
                        connection.execute(
                            "CREATE TRIGGER stop_finish BEFORE UPDATE OF status ON runs "
                            "WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT, 'fault'); END"
                        )
                        connection.commit()
                    finally:
                        connection.close()
                manager = RunManager(
                    store, Agent(Provider(), RunSettings(request_timeout=0.03), streaming=True)
                )
                handle = await manager.submit(sid, "first")
                await asyncio.wait_for(entered.wait(), 2)
                if mode == "cancel":
                    await manager.cancel(handle.run_id, "user")
                await asyncio.wait_for(handle.done.wait(), 2)
                self.assertTrue(closed.is_set())
                self.assertEqual([r.message.role for r in await store.load_history(sid)], ["user"])
                events = []
                while not handle.events.empty():
                    events.append(handle.events.get_nowait())
                self.assertTrue(any(e["type"] == "llm.delta" for e in events))
                await store.close()
                if mode == "commit":
                    connection = sqlite3.connect(store.path)
                    try:
                        connection.execute("DROP TRIGGER stop_finish")
                        connection.commit()
                    finally:
                        connection.close()
                await store.open()
                await store.recover_interrupted()
                seen = []

                class Next:
                    async def complete(self, messages, *, tools=()):
                        seen.extend(messages)
                        return ModelReply(message=Message(role="assistant", content="next"))

                next_manager = RunManager(store, Agent(Next()))
                next_run = await next_manager.submit(sid, "continue")
                await asyncio.wait_for(next_run.done.wait(), 2)
                self.assertFalse(any(m.content == "不得保存的半截文本" for m in seen))
            finally:
                await store.close()
