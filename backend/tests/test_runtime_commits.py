import unittest

from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.runtime.session import Session
from herta_agent.runtime.turn import MemoryTurn
from herta_agent.tools.echo import echo_registry


class RecordingTurn(MemoryTurn):
    def __init__(self, session, fail=None):
        super().__init__(session)
        self.trace = []
        self.fail = fail

    async def begin(self, user):
        self.trace.append("begin")
        await super().begin(user)

    async def set_context(self, context_hash):
        self.trace.append("context")
        await super().set_context(context_hash)

    async def append(self, message, **kwargs):
        self.trace.append(message.role)
        if self.fail == message.role:
            raise RuntimeError("commit failed")
        await super().append(message, **kwargs)

    async def complete(self, message, **kwargs):
        self.trace.append("complete")
        if self.fail == "complete":
            raise RuntimeError("commit failed")
        await super().complete(message, **kwargs)

    async def abort(self, **kwargs):
        self.trace.append("abort")
        await super().abort(**kwargs)


class Provider:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, *, tools=()):
        self.calls += 1
        return ModelReply(
            message=(
                Message(
                    role="assistant",
                    tool_calls=(ToolCall(id="a", name="echo", arguments='{"text":"x"}'),),
                )
                if self.calls == 1
                else Message(role="assistant", content="done")
            )
        )


class CommitTests(unittest.IsolatedAsyncioTestCase):
    async def test_submission_order_and_failures_stop_loop(self):
        for fail in (None, "assistant", "tool", "complete"):
            with self.subTest(fail=fail):
                session, provider = Session(), Provider()
                turn = RecordingTurn(session, fail)
                agent = Agent(provider, registry=echo_registry())
                if fail:
                    with self.assertRaises(RuntimeError):
                        await agent.run(session, "go", turn_io=turn)
                    self.assertEqual(turn.trace.count("abort"), 1)
                    self.assertEqual(provider.calls, 2 if fail == "complete" else 1)
                    self.assertFalse(any(m.content == "done" for m in session.history))
                    if fail == "assistant":
                        self.assertEqual([m.role for m in session.history], ["user"])
                else:
                    await agent.run(session, "go", turn_io=turn)
                    self.assertEqual(
                        turn.trace, ["begin", "context", "assistant", "tool", "complete"]
                    )

    async def test_persona_error_preserves_user_and_aborts_once(self):
        class MissingContext:
            def snapshot(self):
                raise ContextError("missing")

        session, provider = Session(), Provider()
        turn = RecordingTurn(session)
        with self.assertRaises(ContextError):
            await Agent(provider, context_builder=MissingContext()).run(session, "go", turn_io=turn)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(turn.trace, ["begin", "abort"])
        self.assertEqual(session.history, (Message(role="user", content="go"),))

    async def test_restore_validates_and_does_not_share_lists(self):
        history = [
            Message(role="user", content="previous"),
            Message(role="assistant", content="done"),
        ]
        first = Session.restore("first", history)
        second = Session.restore("second", history)
        first.begin_turn(Message(role="user", content="new"))
        self.assertEqual(second.history, tuple(history))
        for invalid in (
            [Message(role="system", content="bad")],
            [Message(role="assistant", content="bad")],
            [
                Message(role="user", content="x"),
                Message(role="tool", content="x", tool_call_id="a"),
            ],
            [
                Message(role="user", content="x"),
                Message(
                    role="assistant", tool_calls=(ToolCall(id="a", name="echo", arguments="{}"),)
                ),
            ],
            history + [Message(role="assistant", content="extra")],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Session.restore("bad", invalid)
