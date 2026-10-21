"""Offline subprocess fixture only; never used by the production entry point."""

import asyncio
import os
import socket
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from herta_agent.config import RunSettings
from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.tools.echo import EchoParameters
from herta_agent.tools.registry import ToolSpec


def main():
    # The Windows venv executable is a launcher. Terminate the actual interpreter
    # without running finally/lifespan, then let the launcher reap it normally.
    def hard_exit():
        sys.stdin.buffer.read(1)
        os._exit(91)

    threading.Thread(target=hard_exit, daemon=True).start()
    root = Path(sys.argv[1])

    class Provider:
        async def stream(self, messages, *, tools=()):
            text = next(m.content for m in reversed(messages) if m.role == "user")
            yield TextDelta("partial")
            if text == "wait":
                await asyncio.Event().wait()
            elif text == "flood":
                for _ in range(10000):
                    yield TextDelta("x" * 64000)
            elif text == "tools" and messages[-1].role != "tool":
                yield ReplyCompleted(
                    ModelReply(
                        message=Message(
                            role="assistant",
                            tool_calls=(
                                ToolCall(id="a", name="record", arguments='{"text":"done"}'),
                                ToolCall(id="b", name="record", arguments='{"text":"wait"}'),
                            ),
                        )
                    )
                )
                return
            yield ReplyCompleted(
                ModelReply(message=Message(role="assistant", content="saved answer"))
            )

    settings = ServiceSettings(
        db_path=root / "sessions.sqlite3",
        max_active_runs=2,
        send_wait_seconds=0.2,
        event_wait_seconds=0.2,
        heartbeat_seconds=0.1,
        run=RunSettings(tool_timeout=60.0),
    )
    app = create_app(settings, provider=Provider())
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original_lifespan(app):

            async def record(args):
                with (root / "tool-count").open("a", encoding="utf-8") as stream:
                    stream.write(args.text + "\n")
                if args.text == "wait":
                    await asyncio.Event().wait()
                return "saved"

            app.state.manager.agent.registry.register(
                ToolSpec("record", "Fixture", EchoParameters, record)
            )
            admit = app.state.store.admit_run

            async def gated_admit(*args):
                if (root / "delay-admission").exists():
                    (root / "admission-entered").touch()
                    while (root / "delay-admission").exists():  # noqa: ASYNC110 - cross-process file gate
                        await asyncio.sleep(0.01)
                return await admit(*args)

            app.state.store.admit_run = gated_admit
            yield

    app.router.lifespan_context = lifespan
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        ready = root / "port.tmp"
        ready.write_text(str(sock.getsockname()[1]), encoding="ascii")
        ready.replace(root / "port.txt")
        uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", access_log=False, log_level="warning")
        ).run(sockets=[sock])


if __name__ == "__main__":
    main()
