import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from test_tool_loop import ScriptedProvider

from herta_agent.persona import PersonaContextBuilder
from herta_agent.rag.errors import RagError
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.messages import Message, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import EchoParameters, echo
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry, ToolSpec
from herta_agent.tools.search_knowledge import search_knowledge_spec


def call(arguments='{"query":"黑塔"}'):
    return ToolCall(id="knowledge", name="search_knowledge", arguments=arguments)


def registry_for(retriever=None, **kwargs):
    registry = ToolRegistry()
    registry.register(search_knowledge_spec(retriever, **kwargs))
    return registry


class Retriever:
    async def search(self, query):
        return {"query": query, "results": [{"chunk_id": "fact-1", "text": "事实"}]}


class RagToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_strict_and_query_trim(self):
        registry = registry_for(Retriever())
        schema = registry.definitions()[0]["function"]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["query"])
        executor = ToolExecutor(registry)
        result = await executor.execute(call('{"query":"  黑塔  "}'))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["query"], "黑塔")
        for args in (
            {},
            {"query": 1},
            {"query": True},
            {"query": "  "},
            {"query": "x" * 1001},
            {"query": "x", "extra": 1},
        ):
            with self.subTest(args=args):
                result = await executor.execute(call(json.dumps(args)))
                self.assertEqual(result.error.code, "invalid_arguments")
        self.assertTrue((await executor.execute(call(json.dumps({"query": "x" * 1000})))).ok)

    async def test_missing_and_expected_errors_are_outer_failures(self):
        result = await ToolExecutor(registry_for()).execute(call())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "index_missing")
        result = await ToolExecutor(
            registry_for(unavailable=RagError("index_stale", "索引需要更新。"))
        ).execute(call())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "index_stale")

        class FailedRetriever:
            async def search(self, query):
                raise RagError("embedding_failed", "嵌入服务不可用。")

        result = await ToolExecutor(registry_for(FailedRetriever())).execute(call())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "embedding_failed")
        self.assertEqual(result.error.message, "嵌入服务不可用。")

    async def test_unknown_exception_and_invalid_output_are_sanitized(self):
        class FailedRetriever:
            async def search(self, query):
                raise RuntimeError("private-key")

        class InvalidRetriever:
            async def search(self, query):
                return {"score": float("nan")}

        for retriever in (FailedRetriever(), InvalidRetriever()):
            result = await ToolExecutor(registry_for(retriever)).execute(call())
            self.assertEqual(result.error.code, "execution_error")
            self.assertNotIn("private-key", result.to_json())

    async def test_deadline_override_and_global_default(self):
        class SlowRetriever:
            async def search(self, query):
                await asyncio.sleep(0.03)
                return {"results": []}

        registry = registry_for(SlowRetriever(), timeout=0.3)
        registry.register(ToolSpec("echo", "Echo", EchoParameters, echo))
        executor = ToolExecutor(registry, timeout=0.005)
        self.assertTrue((await executor.execute(call())).ok)
        result = await executor.execute(
            ToolCall(id="echo", name="echo", arguments='{"text":"x","delay_seconds":0.1}')
        )
        self.assertEqual(result.error.code, "timeout")
        result = await ToolExecutor(registry_for(SlowRetriever(), timeout=0.005)).execute(call())
        self.assertEqual(result.error.code, "timeout")

    def test_timeout_validation(self):
        for value in (True, False, 0, -1, float("nan"), float("inf"), 601, "20"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ToolSpec("echo", "Echo", EchoParameters, echo, timeout=value)
        self.assertIsNone(ToolSpec("echo", "Echo", EchoParameters, echo).timeout)

    async def test_agent_evidence_keeps_persona_and_failure_allows_reuse(self):
        for retriever in (Retriever(), None):
            provider = ScriptedProvider(
                Message(role="assistant", tool_calls=(call(),)),
                Message(role="assistant", content="回答 [fact-1]"),
                Message(role="assistant", content="继续"),
            )
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "soul.md"
                path.write_text("完整人格快照", encoding="utf-8")
                agent = Agent(
                    provider,
                    registry=registry_for(retriever),
                    context_builder=PersonaContextBuilder(path),
                )
                session = Session()
                result = await agent.run(session, "黑塔是谁")
                self.assertEqual(result.reply, "回答 [fact-1]")
                self.assertEqual(session.history[2].tool_call_id, "knowledge")
                self.assertEqual(
                    json.loads(session.history[2].content)["ok"], retriever is not None
                )
                await agent.run(session, "继续")
            for messages, _ in provider.requests:
                self.assertEqual(messages[0].content, "完整人格快照")
                self.assertEqual(sum(m.role == "system" for m in messages), 1)

    async def test_cancellation_propagates_closes_tool_pair_and_reuses_session(self):
        started, cleaned = asyncio.Event(), asyncio.Event()

        class WaitingRetriever:
            async def search(self, query):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()

        provider = ScriptedProvider(
            Message(role="assistant", tool_calls=(call(),)),
            Message(role="assistant", content="继续"),
        )
        session = Session()
        agent = Agent(provider, registry=registry_for(WaitingRetriever()))
        task = asyncio.create_task(agent.run(session, "黑塔是谁"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())
        self.assertEqual(session.history[-1].tool_call_id, "knowledge")
        self.assertEqual(json.loads(session.history[-1].content)["error"]["code"], "cancelled")
        self.assertEqual((await agent.run(session, "继续")).reply, "继续")
