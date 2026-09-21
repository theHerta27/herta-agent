import unittest

from test_runtime_commits import RecordingTurn

from herta_agent.runtime.agent import Agent
from herta_agent.runtime.events import RuntimeEvent
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import echo_registry
from herta_agent.tools.executor import ToolExecutor


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_follow_commits_and_only_valid_tools_start(self):
        session = Session()
        calls = tuple(
            ToolCall(id=str(i), name=name, arguments=args)
            for i, (name, args) in enumerate(
                [("echo", '{"text":"x"}'), ("missing", "{}"), ("echo", "{")]
            )
        )
        replies = iter(
            [Message(role="assistant", tool_calls=calls), Message(role="assistant", content="done")]
        )

        class Provider:
            async def complete(self, messages, *, tools=()):
                return ModelReply(message=next(replies))

        events = []

        class Sink:
            async def emit(self, event):
                events.append((event, session.history))

        await Agent(Provider(), registry=echo_registry()).run(session, "go", observer=Sink())
        self.assertEqual(
            [e.type for e, _ in events],
            [
                "llm.started",
                "llm.completed",
                "tool.started",
                "tool.completed",
                "tool.failed",
                "tool.failed",
                "llm.started",
                "llm.completed",
            ],
        )
        self.assertEqual(events[1][1][-1].tool_calls, calls)
        self.assertEqual(events[3][1][-1].role, "tool")
        self.assertEqual(events[-1][1][-1].content, "done")
        self.assertEqual(events[0][0].message_id, events[1][0].message_id)
        self.assertNotEqual(events[0][0].message_id, events[-1][0].message_id)
        self.assertTrue(events[3][0].payload["result"]["ok"])
        self.assertEqual(events[4][0].payload["result"]["error"]["code"], "unknown_tool")
        self.assertIsInstance(events[0][0], RuntimeEvent)

    async def test_start_callback_error_is_infrastructure_failure(self):
        async def broken():
            raise RuntimeError("sink failed")

        executor = ToolExecutor(echo_registry())
        with self.assertRaises(RuntimeError):
            await executor.execute(
                ToolCall(id="a", name="echo", arguments='{"text":"x"}'), on_started=broken
            )

    async def test_no_completed_event_when_commit_fails(self):
        session = Session()

        class Provider:
            async def complete(self, messages, *, tools=()):
                return ModelReply(message=Message(role="assistant", content="done"))

        events = []

        class Sink:
            async def emit(self, event):
                events.append(event.type)

        with self.assertRaises(RuntimeError):
            await Agent(Provider()).run(
                session, "go", turn_io=RecordingTurn(session, "complete"), observer=Sink()
            )
        self.assertEqual(events, ["llm.started"])
