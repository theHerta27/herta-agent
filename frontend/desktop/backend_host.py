"""Desktop-owned stdio lifecycle adapter; no Agent/Store business logic here."""

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

import uvicorn
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings


async def serve(db_path: Path):
    # Preserve private settings excluded from public serialization (workspace token).
    settings = ServiceSettings.from_env().model_copy(update={"db_path": db_path, "port": 0})
    app = create_app(settings)
    stopping = asyncio.Event()
    startup_finished = asyncio.Event()
    loop = asyncio.get_running_loop()

    def read_commands():
        # EOF includes an unexpectedly closed parent pipe. No POSIX signals required.
        while line := sys.stdin.buffer.readline(4097):
            try:
                command = json.loads(line)
            except (ValueError, UnicodeError):
                break
            if command == {"type": "shutdown", "protocol": 1}:
                break
        loop.call_soon_threadsafe(stopping.set)

    class DesktopServer(uvicorn.Server):
        async def startup(self, sockets=None):
            try:
                await super().startup(sockets)
            finally:
                startup_finished.set()
            if self.started:
                port = self.servers[0].sockets[0].getsockname()[1]
                print(
                    json.dumps({"type": "ready", "protocol": 1, "port": port, "pid": os.getpid()}),
                    flush=True,
                )

    server = DesktopServer(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            workers=1,
            access_log=False,
            log_config=None,
            timeout_graceful_shutdown=5,
        )
    )
    threading.Thread(target=read_commands, daemon=True).start()
    serving = asyncio.create_task(server.serve())
    serving.add_done_callback(lambda _: startup_finished.set())
    requested = asyncio.create_task(stopping.wait())
    try:
        done, _ = await asyncio.wait((serving, requested), return_when=asyncio.FIRST_COMPLETED)
        if requested in done:
            # Let startup finish so shutdown owns the fully assembled manager.
            await startup_finished.wait()
            manager = getattr(app.state, "manager", None)
            try:
                if manager is not None:
                    await manager.shutdown()
            finally:
                server.should_exit = True
        await serving
    finally:
        requested.cancel()
        await asyncio.gather(requested, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(serve(args.db.resolve()))
    except Exception:
        # This channel is private and deliberately excludes exception/config details.
        print('{"type":"error","protocol":1,"code":"host_failed"}', flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
