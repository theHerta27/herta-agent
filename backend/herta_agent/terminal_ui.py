"""Inline terminal presentation. It observes the existing loop and returns approval only."""

import subprocess
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from herta_agent.tools.permissions import terminal_text

STYLE = Style.from_dict({"prompt": "bold #b48aff", "selected": "reverse bold", "hint": "#888888"})
TOOL_LABELS = {
    "grep_code": "搜索代码",
    "read_file": "读取文件",
    "edit_file": "修改文件",
    "create_file": "新建文件",
    "run_tests": "运行测试",
}


def safe(value, limit=240):
    return terminal_text(str(value)[:limit]).replace("\r", "\\r").replace("\n", "\\n")


class TerminalUI:
    def __init__(self, *, console=None, input=None, output=None, trace=None):
        self.console = console if console is not None else Console()
        self.input, self.output, self.trace = input, output, trace
        self.waiting = None
        self._prompt = None
        self._details = None
        self._confirm_label = "确认修改"

    def welcome(self, root: Path, model: str, *, demo=False):
        title = Text("✦ Herta Agent", style="bold magenta")
        body = Text(f"项目：{safe(root.name or root)}\n模型：{safe(model)}\n")
        if demo:
            body.append("离线演示：固定回答，不调用模型\n", style="yellow")
        body.append("输入任务即可开始；/exit 退出，Ctrl+C 取消当前轮。", style="dim")
        self.console.print(Panel(Group(title, body), border_style="magenta", padding=(0, 1)))

    def session_info(self, session_id, database, *, restored=0):
        if restored:
            self.note(f"已恢复{restored}条历史；修改和测试仍会单独询问你。")
        else:
            self.note("对话会自动保存在本机。")
        if self.trace is not None:
            self.note(f"会话：{safe(session_id)}\n数据库：{safe(database)}")

    def note(self, text):
        self.console.print(Text(terminal_text(text), style="dim"))

    def error(self, text):
        self.stop_wait()
        self.console.print(Text("未完成：" + terminal_text(text), style="bold red"))

    def answer(self, text):
        self.stop_wait()
        self.console.print()
        self.console.print(Text("Herta", style="bold magenta"))
        self.console.print(Markdown(terminal_text(text), code_theme="ansi_dark"))
        self.console.print()

    def _input_prompt(self):
        if self._prompt is None:
            keys = KeyBindings()

            @keys.add("enter")
            def send(event):
                event.current_buffer.validate_and_handle()

            @keys.add("escape", "enter")
            def newline(event):
                event.current_buffer.insert_text("\n")

            self._prompt = PromptSession(
                message=FormattedText([("class:prompt", "› ")]),
                multiline=True,
                key_bindings=keys,
                history=InMemoryHistory(),
                prompt_continuation="· ",
                bottom_toolbar="Enter 发送 · Esc再Enter 换行 · ↑↓ 历史 · /exit 退出",
                style=STYLE,
                input=self.input,
                output=self.output,
            )
        return self._prompt

    def read(self):
        self.stop_wait()
        return self._input_prompt().prompt()

    async def read_async(self):
        self.stop_wait()
        return await self._input_prompt().prompt_async()

    def preview_change(self, path, diff, *, created=False):
        self.stop_wait()
        self._details = None
        self._confirm_label = "确认新建" if created else "确认修改"
        self.console.print(
            Panel(
                Syntax(
                    terminal_text(diff),
                    "diff",
                    theme="ansi_dark",
                    background_color="default",
                    word_wrap=True,
                ),
                title=Text(("准备新建 " if created else "准备修改 ") + safe(path)),
                subtitle="尚未写入；绿色新增，红色删除",
                border_style="yellow",
            )
        )

    def preview_test(self, root, command):
        self.stop_wait()
        self._details = terminal_text(subprocess.list2cmdline(command))
        self._confirm_label = "确认运行"
        # The last worker arguments are root/start/pattern/report. Show the exact scope.
        scope = command[-3] if len(command) >= 9 else command[-1]
        pattern = command[-2] if len(command) >= 9 else "test*.py"
        self.console.print(
            Panel(
                Text(
                    f"项目：{terminal_text(str(root))}\n测试目录：{safe(scope)}\n"
                    f"匹配：{safe(pattern)}\n方式：当前CLI环境的Python unittest\n"
                    "会执行项目代码，具有当前账号权限；不是沙箱。\n按 D 可查看完整程序和参数。"
                ),
                title="准备运行测试",
                border_style="yellow",
            )
        )

    async def confirm(self):
        self.stop_wait()
        selected = False
        keys = KeyBindings()

        @keys.add("left")
        @keys.add("right")
        @keys.add("tab")
        def choose(event):
            nonlocal selected
            selected = not selected

        @keys.add("enter")
        def submit(event):
            typed = event.current_buffer.text.strip().lower()
            event.app.exit(result=(typed == "yes" if typed else selected))

        @keys.add("d")
        @keys.add("D")
        def details(event):
            event.app.exit(result="details")

        def choices():
            return FormattedText(
                [
                    ("", "←→ 选择，Enter 确认；也可输入 yes 后回车。默认取消。\n  "),
                    (
                        "class:selected" if not selected else "",
                        " ● 取消 " if not selected else " ○ 取消 ",
                    ),
                    ("", "   "),
                    (
                        "class:selected" if selected else "",
                        f" {'●' if selected else '○'} {self._confirm_label} ",
                    ),
                    ("", " "),
                ]
            )

        prompt = PromptSession(
            message=choices,
            key_bindings=keys,
            style=STYLE,
            bottom_toolbar="←→ 选择 · Enter 确认 · 默认取消 · Ctrl+C 拒绝",
            input=self.input,
            output=self.output,
        )
        try:
            while True:
                result = await prompt.prompt_async()
                if result != "details":
                    # prompt_toolkit's dumb-terminal fallback returns text, bypassing keys.
                    allowed = result is True or (
                        isinstance(result, str) and result.strip().lower() == "yes"
                    )
                    if not allowed:
                        self.note("未确认，此次操作已取消。")
                    return allowed
                selected = False
                self.console.print(Text(self._details or "此次操作的完整差异已显示在上方。"))
        except (EOFError, KeyboardInterrupt):
            self.note("未确认，此次操作已取消。")
            return False

    def stop_wait(self):
        if self.waiting is not None:
            self.waiting.stop()
            self.waiting = None

    async def emit(self, event):
        if self.trace is not None:
            await self.trace.emit(event)
        payload = event.payload
        if event.type == "llm.started":
            self.stop_wait()
            self.waiting = self.console.status("正在等待模型回复…", spinner="dots")
            self.waiting.start()
            return
        if event.type == "llm.completed":
            self.stop_wait()
            return
        name = payload.get("name")
        action = TOOL_LABELS.get(name, "执行工具")
        if event.type == "tool.started":
            self.console.print(Text("· 正在" + action + "…", style="dim"))
        elif event.type in ("tool.completed", "tool.failed"):
            self.stop_wait()
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                return
            if event.type == "tool.failed":
                error = result.get("error") or {}
                code = error.get("code") if isinstance(error, dict) else None
                if code == "permission_denied":
                    self.note("— " + action + "未获确认，没有执行。")
                else:
                    self.error(action + "失败（" + safe(code or "unknown") + "）。")
                return
            data = result.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            if name == "run_tests":
                status = data.get("status")
                if status == "passed":
                    self.console.print(
                        Text(f"✓ 测试通过（{safe(data.get('tests_run', '?'))}个）", style="green")
                    )
                elif status == "failed":
                    self.error("测试未通过，请查看Herta对失败原因的说明。")
                else:
                    self.console.print(
                        Text("— 未确认测试通过（无测试、存在跳过或报告不完整）。", style="yellow")
                    )
            else:
                label = {
                    "read_file": "已读取",
                    "grep_code": "已完成代码搜索",
                    "edit_file": "已修改",
                    "create_file": "已新建",
                }.get(name, "工具已执行")
                path = " " + safe(data["path"]) if isinstance(data.get("path"), str) else ""
                self.console.print(Text("✓ " + label + path, style="green"))
