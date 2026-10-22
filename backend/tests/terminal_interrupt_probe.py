"""A child process: prompt input -> model/tool SIGINT -> another usable prompt."""

import asyncio
import io
import signal
import threading

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from herta_agent.cli import chat
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.terminal_ui import TerminalUI
from herta_agent.tools.registry import ToolParameters, ToolRegistry, ToolSpec

with create_pipe_input() as pipe, asyncio.Runner() as runner:

    async def interrupt(label, next_text):
        timer = threading.Timer(0.05, signal.raise_signal, args=(signal.SIGINT,))
        timer.start()
        try:
            await asyncio.Event().wait()
        finally:
            timer.cancel()
            pipe.send_text(next_text + "\r")
            print("CLEANED:" + label)

    class Provider:
        async def complete(self, messages, *, tools=()):
            turns = sum(m.role == "user" for m in messages)
            if turns == 1:
                await interrupt("model", "two")
            if turns == 2:
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(ToolCall(id="w", name="wait", arguments="{}"),),
                    )
                )
            pipe.send_text("/exit\r")
            print("RESUMED:turns=" + str(turns))
            return ModelReply(message=Message(role="assistant", content="恢复成功"))

    async def wait(parameters):
        await interrupt("tool", "three")

    registry = ToolRegistry()
    registry.register(ToolSpec("wait", "wait", ToolParameters, wait))
    ui = TerminalUI(console=Console(file=io.StringIO()), input=pipe, output=DummyOutput())
    pipe.send_text("one\r")
    chat(Agent(Provider(), registry=registry), None, runner, terminal=ui, observer=ui)
    assert ui.waiting is None
