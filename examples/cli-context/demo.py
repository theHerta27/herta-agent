"""Observe real context selection with the existing fixed Read provider, never an LLM."""

import argparse
import asyncio
import tempfile
from pathlib import Path

from herta_agent.cli import create_agent, print_result, run_turn
from herta_agent.cli_events import TerminalEventSink
from herta_agent.config import RunSettings
from herta_agent.llm.demo import ReadDemoProvider
from herta_agent.runtime.context_engine import ContextSettings
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.paths import Repository


class ObservedReadFixture(ReadDemoProvider):
    def __init__(self):
        super().__init__("note.md")
        self.inputs = []

    async def complete(self, messages, *, tools=()):
        self.inputs.append(messages)
        return await super().complete(messages, tools=tools)


def main():
    parser = argparse.ArgumentParser(description="离线观察完整轮次选择，不调用模型")
    parser.add_argument("--context-window", type=int, default=8192)
    args = parser.parse_args()
    try:
        settings = RunSettings(
            context=ContextSettings(window_tokens=args.context_window)
        )
    except ValueError:
        parser.error("窗口无效；请使用2304以上、不超过2000000的整数。")
    print(
        "离线固定Read脚本：三轮新建的模拟背景资料；不调用模型、不读取API Key。",
        flush=True,
    )
    print("每轮实际读取自己的临时笔记，无须yes；历史节录是程序摘取片段。", flush=True)
    print(f"本机总窗口={args.context_window}，预留输出2048、安全余量256。", flush=True)
    with tempfile.TemporaryDirectory(prefix="herta-context-demo-") as folder:
        root = Path(folder)
        (root / "note.md").write_text("演示笔记。", encoding="utf-8")
        provider, session = ObservedReadFixture(), Session()
        agent = create_agent(provider, settings, Repository(root))
        with asyncio.Runner() as runner:
            for number in range(1, 4):
                print(f"开始任务{number}（背景内容不在终端展开）：", flush=True)
                result = runner.run(
                    run_turn(
                        agent,
                        session,
                        f"任务{number}\n" + "背景资料" * 200,
                        observer=TerminalEventSink(),
                    )
                )
                print_result(result)
                messages = provider.inputs[-1]
                tasks = [
                    m.content.splitlines()[0]
                    for m in messages
                    if m.role == "user" and m.content.startswith("任务")
                ]
                excerpt = any(
                    m.content and m.content.startswith("历史资料节录") for m in messages
                )
                print(
                    f"Provider收到的完整任务轮次：{tasks}；另有历史节录：{excerpt}",
                    flush=True,
                )
        paired = all(
            [call.id for message in messages for call in message.tool_calls]
            == [message.tool_call_id for message in messages if message.role == "tool"]
            for messages in provider.inputs
        )
        print(f"Session保存的原始消息数：{len(session.history)}", flush=True)
        print(f"Provider输入中的工具调用与结果始终配对：{paired}", flush=True)


if __name__ == "__main__":
    main()
