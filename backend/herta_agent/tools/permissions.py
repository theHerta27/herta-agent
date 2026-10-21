"""One-call terminal approval for CLI edits, selected instead of the legacy spec policy."""

import asyncio
import signal

from herta_agent.tools.coding.edit_file import EditParameters, prepare_edit
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.registry import ToolParameters, ToolSpec


def terminal_text(text: str) -> str:
    """Display untrusted text without executing terminal control sequences."""
    return "".join(
        character if character.isprintable() or character in "\n\t" else ascii(character)[1:-1]
        for character in text
    )


class TerminalApproval:
    def __init__(self, repo: Repository):
        self.repo = repo

    async def __call__(self, spec: ToolSpec, parameters: ToolParameters) -> bool:
        if spec.name != "edit_file" or not isinstance(parameters, EditParameters):
            return False
        change = await asyncio.to_thread(prepare_edit, self.repo, parameters)
        print("本次编辑差异（未写入；终端控制字符已转义）：")
        print(terminal_text(change.diff))
        try:
            previous_handler = signal.signal(signal.SIGINT, signal.default_int_handler)
        except ValueError:
            return False  # Terminal prompts belong to the main thread.
        try:
            # Runner's normal first SIGINT only cancels an async task; it cannot wake
            # blocking input. Temporarily use KeyboardInterrupt, then restore Runner.
            answer = input(  # noqa: ASYNC250 - sequential CLI pauses here; no input worker to leak.
                "输入 yes 仅确认本次修改；其他输入或直接回车拒绝："
            )
            return answer.strip().lower() == "yes"
        except (EOFError, KeyboardInterrupt):
            print("\n未确认，本次修改已拒绝。")
            return False
        finally:
            signal.signal(signal.SIGINT, previous_handler)
