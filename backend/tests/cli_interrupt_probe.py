"""Run in a child process so SIGINT cannot interrupt the unittest runner."""

import asyncio
import json
import signal
import sys
import threading
from unittest.mock import patch

from herta_agent.cli import chat, main
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.echo import EchoParameters, echo_registry
from herta_agent.tools.registry import ToolSpec


async def interrupt_wait(label):
    timer = threading.Timer(0.05, signal.raise_signal, args=(signal.SIGINT,))
    timer.start()
    try:
        await asyncio.Event().wait()
    finally:
        timer.cancel()
        print(f"CLEANED:{label}")


class Provider:
    async def complete(self, messages, *, tools=()):
        turns = sum(message.role == "user" for message in messages)
        if turns == 1:
            await interrupt_wait("model")
        if turns == 2:
            return ModelReply(
                message=Message(
                    role="assistant",
                    tool_calls=(ToolCall(id="cancel", name="wait", arguments='{"text":"x"}'),),
                )
            )
        results = [json.loads(message.content) for message in messages if message.role == "tool"]
        assert len(results) == 1 and results[0]["error"]["code"] == "cancelled", results
        return ModelReply(message=Message(role="assistant", content=f"RESUMED:turns={turns}"))


async def wait(parameters):
    await interrupt_wait("tool")


if "--single" in sys.argv:
    with (
        patch("herta_agent.cli.DemoProvider", return_value=Provider()),
        patch("sys.argv", ["herta_agent", "--message", "one"]),
    ):
        main()
    raise AssertionError("Single-message cancellation should exit with status 130")

registry = echo_registry()
registry.register(ToolSpec("wait", "Wait", EchoParameters, wait))
with (
    asyncio.Runner() as runner,
    patch("builtins.input", side_effect=["one", "two", "three", "/exit"]),
):
    chat(Agent(Provider(), registry=registry), None, runner)
