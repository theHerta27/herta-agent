"""One-call terminal approval for CLI edits, selected instead of the legacy spec policy."""

import asyncio
import signal
import subprocess
from pathlib import Path

from herta_agent.tools.coding.create_file import CreateParameters, prepare_create
from herta_agent.tools.coding.edit_file import EditParameters, prepare_edit
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.coding.run_tests import TestParameters, test_command
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
        if spec.name == "edit_file" and isinstance(parameters, EditParameters):
            change = await asyncio.to_thread(prepare_edit, self.repo, parameters)
            print("本次编辑差异（未写入；终端控制字符已转义）：")
            print(terminal_text(change.diff))
        elif spec.name == "create_file" and isinstance(parameters, CreateParameters):
            change = await asyncio.to_thread(prepare_create, self.repo, parameters)
            print("本次新建差异（未写入；终端控制字符已转义）：")
            print(terminal_text(change.diff))
        elif spec.name == "run_tests" and isinstance(parameters, TestParameters):
            command = test_command(self.repo, parameters, Path("<owned-temporary-report>"))
            print("本次测试工作目录：" + terminal_text(str(self.repo.root)))
            print("实际程序及参数（报告路径执行时由程序临时创建）：")
            print(terminal_text(subprocess.list2cmdline(command)))
            print("将执行该项目的Python代码，具有当前账号权限；这不是沙箱。")
        else:
            return False
        return confirm_once()


def confirm_once() -> bool:
    try:
        previous_handler = signal.signal(signal.SIGINT, signal.default_int_handler)
    except ValueError:
        return False  # Terminal prompts belong to the main thread.
    try:
        # Runner's normal first SIGINT only cancels an async task; it cannot wake
        # blocking input. Temporarily use KeyboardInterrupt, then restore Runner.
        answer = input(  # noqa: ASYNC250 - sequential CLI pauses here; no input worker to leak.
            "输入 yes 仅确认本次操作；其他输入或直接回车拒绝："
        )
        return answer.strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        print("\n未确认，本次操作已拒绝。")
        return False
    finally:
        signal.signal(signal.SIGINT, previous_handler)
