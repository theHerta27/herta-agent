import asyncio
import unittest

from pydantic import ValidationError

from herta_agent.config import ProviderSettings, RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.agent import DEFAULT_SYSTEM, Agent
from herta_agent.runtime.errors import ModelTimeoutError, ProviderError, SessionBusyError
from herta_agent.runtime.messages import Message, ModelReply
from herta_agent.runtime.session import Session


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[Message, ...]] = []

    async def complete(self, messages: tuple[Message, ...]) -> ModelReply:
        self.calls.append(messages)
        return ModelReply(message=Message(role="assistant", content="answer"))


class WaitingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cleaned_up = False

    async def complete(self, messages: tuple[Message, ...]) -> ModelReply:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cleaned_up = True
        raise AssertionError("unreachable")


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_turn_receives_ordered_history_and_one_system_message(self) -> None:
        provider = RecordingProvider()
        agent, session = Agent(provider), Session()
        first = await agent.run(session, "first")
        second = await agent.run(session, "second")
        self.assertEqual((first.steps, second.steps), (1, 1))
        self.assertEqual(second.session_id, session.session_id)
        self.assertEqual(
            [(m.role, m.content) for m in provider.calls[1]],
            [
                ("system", DEFAULT_SYSTEM),
                ("user", "first"),
                ("assistant", "answer"),
                ("user", "second"),
            ],
        )
        self.assertEqual(len(session.history), 4)
        self.assertNotIn("system", [m.role for m in session.history])

    async def test_sessions_do_not_share_history(self) -> None:
        provider = RecordingProvider()
        agent = Agent(provider)
        first, second = Session(), Session()
        await agent.run(first, "private first session")
        await agent.run(second, "new session")
        self.assertEqual(len(provider.calls[1]), 2)
        self.assertNotEqual(first.session_id, second.session_id)

    async def test_history_snapshot_and_messages_cannot_be_mutated(self) -> None:
        session = Session()
        await Agent(RecordingProvider()).run(session, "hello")
        snapshot = session.history
        with self.assertRaises(ValidationError):
            snapshot[0].content = "changed"
        await Agent(RecordingProvider()).run(session, "another")
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(len(session.history), 4)

    async def test_empty_input_does_not_call_provider_or_change_session(self) -> None:
        provider, session = RecordingProvider(), Session()
        with self.assertRaises(ValidationError):
            await Agent(provider).run(session, " \n ")
        self.assertEqual(provider.calls, [])
        self.assertEqual(session.history, ())

    async def test_error_is_not_retried_and_session_is_reusable(self) -> None:
        class BrokenProvider:
            calls = 0

            async def complete(self, messages: tuple[Message, ...]) -> ModelReply:
                self.calls += 1
                raise ProviderError("expected failure")

        provider, session = BrokenProvider(), Session()
        with self.assertRaises(ProviderError):
            await Agent(provider).run(session, "failed input")
        self.assertEqual(provider.calls, 1)
        self.assertEqual([m.role for m in session.history], ["user"])
        await Agent(RecordingProvider()).run(session, "try again")
        self.assertEqual(session.history[-1].role, "assistant")

    async def test_timeout_cleans_provider_and_releases_session(self) -> None:
        provider, session = WaitingProvider(), Session()
        with self.assertRaises(ModelTimeoutError):
            await Agent(provider, RunSettings(request_timeout=0.02)).run(session, "wait")
        self.assertTrue(provider.cleaned_up)
        self.assertEqual(len(session.history), 1)
        await Agent(RecordingProvider()).run(session, "after timeout")

    async def test_cancellation_propagates_without_fake_answer(self) -> None:
        provider, session = WaitingProvider(), Session()
        task = asyncio.create_task(Agent(provider).run(session, "cancel me"))
        await asyncio.wait_for(provider.started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(provider.cleaned_up)
        self.assertEqual([m.role for m in session.history], ["user"])
        await Agent(RecordingProvider()).run(session, "after cancel")

    async def test_same_session_rejects_overlap_before_appending_user(self) -> None:
        provider, session = WaitingProvider(), Session()
        task = asyncio.create_task(Agent(provider).run(session, "first"))
        await asyncio.wait_for(provider.started.wait(), timeout=1)
        try:
            with self.assertRaises(SessionBusyError):
                await Agent(RecordingProvider()).run(session, "overlap")
            self.assertEqual([m.content for m in session.history], ["first"])
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_max_steps_one_allows_exactly_one_request(self) -> None:
        provider = RecordingProvider()
        result = await Agent(provider, RunSettings(max_steps=1)).run(Session(), "hello")
        self.assertEqual(result.steps, 1)
        self.assertEqual(len(provider.calls), 1)

    async def test_demo_explicitly_labels_offline_echo_and_turn_count(self) -> None:
        agent, session = Agent(DemoProvider()), Session()
        await agent.run(session, "first")
        result = await agent.run(session, "你好")
        self.assertIn("离线演示，第 2 轮", result.reply)
        self.assertIn("你好", result.reply)


class ConfigurationTests(unittest.TestCase):
    def test_reject_invalid_budgets_and_nonfinite_deadlines(self) -> None:
        for value in [0, -1, 101, True, 1.5]:
            with self.subTest(max_steps=value), self.assertRaises(ValidationError):
                RunSettings(max_steps=value)
        for value in [0, -1, float("inf"), float("nan"), 601, True]:
            with self.subTest(timeout=value), self.assertRaises(ValidationError):
                RunSettings(request_timeout=value)

    def test_model_reply_cannot_masquerade_as_user_message(self) -> None:
        with self.assertRaises(ValidationError):
            ModelReply(message=Message(role="user", content="wrong role"))

    def test_provider_settings_reject_credentials_in_url_and_bad_endpoint(self) -> None:
        for url in [
            "file:///tmp",
            "https://user:secret@example.test/v1",
            "https://example.test/v1?key=secret",
            "https://example.test/v1#frag",
            "https://example.test/v1/chat/completions",
            "https://example.test:bad/v1",
        ]:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                ProviderSettings(base_url=url, model="example", api_key="secret")

    def test_api_key_is_masked_in_repr_and_configuration_errors(self) -> None:
        settings = ProviderSettings(
            base_url="https://example.test/v1/", model=" example ", api_key="private-key"
        )
        self.assertEqual(settings.base_url, "https://example.test/v1")
        self.assertEqual(settings.model, "example")
        self.assertNotIn("private-key", repr(settings))
        with self.assertRaises(ValidationError) as caught:
            ProviderSettings(base_url="https://private-key@example.test", model="x", api_key="x")
        self.assertNotIn("private-key", str(caught.exception))
