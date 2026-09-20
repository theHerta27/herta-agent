import asyncio
import json
import unittest

from pydantic import ValidationError

from herta_agent.config import RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import StepLimitExceeded, ToolCallLimitExceeded
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import EchoParameters, echo_registry
from herta_agent.tools.registry import ToolSpec


def call(id="a", name="echo", arguments='{"text":"你好"}'):
    return ToolCall(id=id, name=name, arguments=arguments)


class ScriptedProvider:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []

    async def complete(self, messages, *, tools=()):
        self.requests.append((messages, tools))
        return ModelReply(message=next(self.replies))


class ToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_steps_and_tool_errors_are_fed_back_in_order(self):
        provider = ScriptedProvider(
            Message(role="assistant", tool_calls=(call(), call("b", "unknown"))),
            Message(role="assistant", tool_calls=(call("c", arguments="{"),)),
            Message(role="assistant", content="done"),
        )
        session = Session()
        result = await Agent(provider, registry=echo_registry()).run(session, "go")
        self.assertEqual((result.steps, result.reply), (3, "done"))
        self.assertEqual(
            [m.role for m in session.history],
            ["user", "assistant", "tool", "tool", "assistant", "tool", "assistant"],
        )
        feedback = [m for m in provider.requests[-1][0] if m.role == "tool"]
        self.assertEqual([m.tool_call_id for m in feedback], ["a", "b", "c"])
        self.assertEqual(json.loads(feedback[0].content)["data"], {"text": "你好"})
        self.assertEqual(json.loads(feedback[1].content)["error"]["code"], "unknown_tool")
        self.assertEqual(json.loads(feedback[2].content)["error"]["code"], "invalid_arguments")
        self.assertEqual(provider.requests[0][1][0]["function"]["name"], "echo")

    async def test_budget_closes_last_batch_without_executing_it(self):
        executed = []

        async def record(args):
            executed.append(args.text)
            return args.text

        registry = echo_registry()
        registry.register(ToolSpec("record", "Record", EchoParameters, record))
        provider = ScriptedProvider(
            *[Message(role="assistant", tool_calls=(call(str(i), "record"),)) for i in range(3)]
        )
        session = Session()
        with self.assertRaises(StepLimitExceeded):
            await Agent(provider, RunSettings(max_steps=3), registry=registry).run(session, "go")
        self.assertEqual(len(provider.requests), 3)
        self.assertEqual(len(executed), 2)
        self.assertEqual(
            json.loads(session.history[-1].content)["error"]["code"], "max_steps_exceeded"
        )
        await Agent(DemoProvider()).run(session, "continue")

    async def test_oversized_batch_is_closed_without_execution(self):
        executed = []

        async def record(args):
            executed.append(args.text)
            return args.text

        registry = echo_registry()
        registry.register(ToolSpec("record", "Record", EchoParameters, record))
        provider = ScriptedProvider(
            Message(role="assistant", tool_calls=tuple(call(str(i), "record") for i in range(5)))
        )
        session = Session()
        with self.assertRaises(ToolCallLimitExceeded):
            await Agent(provider, registry=registry).run(session, "go")
        self.assertEqual(executed, [])
        self.assertEqual(len(provider.requests), 1)
        results = [json.loads(m.content) for m in session.history if m.role == "tool"]
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r["error"]["code"] == "tool_call_limit" for r in results))

    async def test_cancel_closes_only_pending_calls_and_reuses_session(self):
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def wait(args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        registry = echo_registry()
        registry.register(ToolSpec("wait", "Wait", EchoParameters, wait))
        provider = ScriptedProvider(
            Message(role="assistant", tool_calls=(call(), call("b", "wait"), call("c")))
        )
        session = Session()
        task = asyncio.create_task(Agent(provider, registry=registry).run(session, "go"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())
        self.assertEqual(len(provider.requests), 1)
        results = [json.loads(m.content) for m in session.history if m.role == "tool"]
        self.assertTrue(results[0]["ok"])
        self.assertEqual([r["error"]["code"] for r in results[1:]], ["cancelled", "cancelled"])
        await Agent(DemoProvider()).run(session, "continue")
        self.assertEqual(session.history[-1].role, "assistant")

    async def test_timeout_is_fed_back_then_model_finishes(self):
        provider = ScriptedProvider(
            Message(
                role="assistant", tool_calls=(call(arguments='{"text":"x","delay_seconds":1}'),)
            ),
            Message(role="assistant", content="timed out"),
        )
        session = Session()
        result = await Agent(
            provider, RunSettings(tool_timeout=0.02), registry=echo_registry()
        ).run(session, "go")
        self.assertEqual(result.steps, 2)
        self.assertEqual(json.loads(session.history[2].content)["error"]["code"], "timeout")


class MessageContractTests(unittest.TestCase):
    def test_rejects_invalid_role_fields_and_duplicate_ids(self):
        for fields in [
            {"role": "user", "content": "x", "tool_calls": (call(),)},
            {"role": "assistant", "tool_call_id": "a", "content": "x"},
            {"role": "tool", "content": "{}"},
            {"role": "assistant", "tool_calls": (call(), call())},
            {"role": "assistant", "content": None},
        ]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Message(**fields)

    def test_session_rejects_unmatched_results_and_unclosed_final(self):
        session = Session()
        session.begin_turn(Message(role="user", content="x"))
        session.record_calls(Message(role="assistant", tool_calls=(call(),)))
        with self.assertRaises(ValueError):
            session.record_result("other", "{}")
        with self.assertRaises(ValueError):
            session.complete_turn(Message(role="assistant", content="done"))
        session.record_result("a", "{}")
        with self.assertRaises(ValueError):
            session.record_result("a", "{}")
        session.complete_turn(Message(role="assistant", content="done"))
