"""Send one SIGINT in a child so the parent tests cannot be interrupted."""

import asyncio
import hashlib
import json
import signal
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from herta_agent.cli import create_agent
from herta_agent.config import RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


def waiting_input(prompt):
    timer = threading.Timer(0.05, signal.raise_signal, args=(signal.SIGINT,))
    timer.start()
    try:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            time.sleep(0.01)
        print("INPUT_STALLED")
        return "yes"
    finally:
        timer.cancel()
        timer.join()


async def run(root):
    repo = Repository(root)
    before = b"value = 1\n"
    target = root / "note.py"
    target.write_bytes(before)
    agent = create_agent(DemoProvider(), RunSettings(), repo, authorize=TerminalApproval(repo))
    try:
        result = await agent.executor.execute(
            ToolCall(
                id="edit",
                name="edit_file",
                arguments=json.dumps(
                    {
                        "path": "note.py",
                        "old_text": "value = 1",
                        "new_text": "value = 2",
                        "expected_sha256": hashlib.sha256(before).hexdigest(),
                    }
                ),
            )
        )
        print("VERDICT:" + result.error.code)
    except asyncio.CancelledError:
        print("CANCELLED_AFTER_INPUT_STALLED")
    print("UNCHANGED:" + str(target.read_bytes() == before))


with tempfile.TemporaryDirectory() as folder, patch("builtins.input", side_effect=waiting_input):
    asyncio.run(run(Path(folder)))
