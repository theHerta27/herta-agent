import unittest

from herta_agent.config import RunSettings
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.context import ContextSnapshot, StaticContextBuilder
from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session


class ContextEngineTests(unittest.TestCase):
    def engine(self, **options):
        from herta_agent.runtime.context_engine import ContextEngine, ContextSettings

        return ContextEngine(ContextSettings(**options))

    def test_persona_current_request_and_output_schema_reserve(self):
        engine = self.engine(window_tokens=1024, output_reserve=128, safety_margin=64)
        snapshot = ContextSnapshot("完整人格，不得删除。")
        history = (Message(role="user", content="中文问题"),)
        package = engine.prepare(history, snapshot, tools=({"name": "lookup"},))
        self.assertEqual(package.messages[0].content, snapshot.system_text)
        self.assertEqual(package.messages[-1], history[-1])
        self.assertEqual(package.input_budget, 832)
        self.assertGreater(package.tool_schema_tokens, 0)
        self.assertLessEqual(package.estimated_input_tokens, package.input_budget)
        self.assertEqual(package.persona_hash, snapshot.sha256)

    def test_recent_whole_turns_and_closed_tools_not_partial_history(self):
        call = ToolCall(id="a", name="echo", arguments="{}")
        history = (
            Message(role="user", content="old " * 600),
            Message(role="assistant", tool_calls=(call,)),
            Message(role="tool", tool_call_id="a", content="result"),
            Message(role="assistant", content="old answer"),
            Message(role="user", content="recent"),
            Message(role="assistant", content="recent answer"),
            Message(role="user", content="current"),
        )
        package = self.engine(
            window_tokens=512, output_reserve=64, safety_margin=32, summary_enabled=False
        ).prepare(history, ContextSnapshot("persona"))
        self.assertEqual(package.retained_message_indices, (4, 5, 6))
        self.assertEqual(package.omitted_message_count, 4)
        self.assertFalse(any(m.tool_call_id or m.tool_calls for m in package.messages))
        self.assertEqual(history[0].content, "old " * 600)

    def test_summary_is_extractive_and_has_source_hash_and_range(self):
        history = (
            Message(role="user", content="约定：项目叫星塔。" + "无关闲聊。" * 400),
            Message(role="assistant", content="好的，项目叫星塔。"),
            Message(role="user", content="项目叫什么？"),
        )
        package = self.engine(
            window_tokens=1024, output_reserve=128, safety_margin=64, summary_tokens=240
        ).prepare(history, ContextSnapshot("persona"))
        self.assertEqual(len(package.summaries), 1)
        summary = package.summaries[0]
        self.assertEqual((summary.source_start, summary.source_end), (0, 1))
        self.assertEqual(summary.algorithm, "extractive-v1")
        self.assertEqual(len(summary.source_hash), 64)
        self.assertIn("项目叫星塔", summary.text)
        self.assertIn(summary.text, package.messages[1].content)
        self.assertEqual(package.messages[1].role, "user")
        self.assertLessEqual(package.estimated_input_tokens, package.input_budget)
        again = self.engine(
            window_tokens=1024, output_reserve=128, safety_margin=64, summary_tokens=240
        ).prepare(history, ContextSnapshot("persona"))
        self.assertEqual(summary.summary_id, again.summaries[0].summary_id)

    def test_mandatory_overflow_rejects_without_truncating(self):
        for persona, text in [("人" * 2000, "hi"), ("persona", "字" * 2000)]:
            with self.subTest(persona=len(persona)), self.assertRaises(ContextError):
                self.engine(window_tokens=512, output_reserve=64, safety_margin=32).prepare(
                    (Message(role="user", content=text),), ContextSnapshot(persona)
                )

    def test_unclosed_or_orphan_or_duplicate_tool_results_rejected(self):
        call = ToolCall(id="a", name="echo", arguments="{}")
        user = Message(role="user", content="q")
        assistant = Message(role="assistant", tool_calls=(call,))
        result = Message(role="tool", tool_call_id="a", content="result")
        for history in [
            (user, assistant),
            (user, result),
            (user, assistant, result, result),
            (user, assistant, Message(role="user", content="next")),
        ]:
            with self.subTest(history=history), self.assertRaises(ContextError):
                self.engine().prepare(history, ContextSnapshot("persona"))

    def test_current_tool_group_overflow_fails_whole(self):
        history = (
            Message(role="user", content="q"),
            Message(role="assistant", tool_calls=(ToolCall(id="a", name="echo", arguments="{}"),)),
            Message(role="tool", tool_call_id="a", content="字" * 2000),
        )
        with self.assertRaises(ContextError):
            self.engine(window_tokens=512, output_reserve=64, safety_margin=32).prepare(
                history, ContextSnapshot("persona")
            )

    def test_evidence_refs_only_selected_successful_tool_chunks(self):
        history = (
            Message(role="user", content="q"),
            Message(
                role="assistant", tool_calls=(ToolCall(id="a", name="search", arguments="{}"),)
            ),
            Message(
                role="tool",
                tool_call_id="a",
                content='{"ok":true,"data":{"chunks":[{"id":"K01-C1"}]}}',
            ),
        )
        package = self.engine().prepare(history, ContextSnapshot("persona"))
        self.assertEqual(package.evidence_refs, ("K01-C1",))

    def test_estimator_injectable_and_settings_validate(self):
        from herta_agent.runtime.context_engine import ContextEngine, ContextSettings

        class Estimator:
            name = "fixture"

            def text(self, value):
                return 5

            def messages(self, values):
                return 20 * len(values)

        package = ContextEngine(ContextSettings(), estimator=Estimator()).prepare(
            (Message(role="user", content="q"),), ContextSnapshot("p")
        )
        self.assertEqual(package.estimated_input_tokens, 40)
        self.assertEqual(package.estimator, "fixture")
        for options in [
            dict(window_tokens=True),
            dict(output_reserve=32768),
            dict(summary_tokens=-1),
            dict(summary_enabled="yes"),
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                ContextSettings(**options)

    def test_summary_has_its_own_configured_token_cap(self):
        from herta_agent.runtime.context_engine import ConservativeEstimator

        history = (
            Message(role="user", content="项目叫星塔。" + "x " * 3000),
            Message(role="assistant", content="answer " * 500),
            Message(role="user", content="current"),
        )
        for cap in (64, 128, 256):
            with self.subTest(cap=cap):
                package = self.engine(
                    window_tokens=2048, output_reserve=128, safety_margin=64, summary_tokens=cap
                ).prepare(history, ContextSnapshot("persona"))
                self.assertTrue(
                    all(ConservativeEstimator().text(s.text) <= cap for s in package.summaries)
                )


class ContextEngineRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_request_never_reaches_provider_and_releases_session(self):
        from herta_agent.runtime.context_engine import ContextSettings

        requests = []

        class Provider:
            async def complete(self, messages, *, tools=()):
                requests.append(messages)
                return ModelReply(message=Message(role="assistant", content="answer"))

        agent = Agent(
            Provider(),
            RunSettings(
                context=ContextSettings(window_tokens=512, output_reserve=64, safety_margin=32)
            ),
            context_builder=StaticContextBuilder("p"),
        )
        session = Session()
        with self.assertRaises(ContextError):
            await agent.run(session, "字" * 2000)
        self.assertEqual(requests, [])
        result = await agent.run(session, "retry")
        self.assertEqual(result.reply, "answer")

    async def test_context_diagnostic_precedes_model_with_same_persona(self):
        events = []

        class Provider:
            async def complete(self, messages, *, tools=()):
                return ModelReply(message=Message(role="assistant", content="answer"))

        class Sink:
            async def emit(self, event):
                events.append(event)

        await Agent(Provider()).run(Session(), "q", observer=Sink())
        self.assertEqual(events[0].type, "context.prepared")
        self.assertEqual(events[1].type, "llm.started")
        self.assertNotIn("messages", events[0].payload)
        self.assertNotIn("system_text", events[0].payload)
        self.assertEqual(len(events[0].payload["persona_hash"]), 64)
