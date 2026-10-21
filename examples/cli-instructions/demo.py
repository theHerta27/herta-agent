"""Show actual per-run context input, without claiming that an LLM followed the guidance."""

import asyncio
import json
import tempfile
from pathlib import Path

from herta_agent.cli import create_agent, print_result, run_turn
from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ModelReply
from herta_agent.runtime.session import Session
from herta_agent.tools.coding.paths import Repository


class InspectContextFixture:
    async def complete(self, messages, *, tools=()):
        # Only this demonstration knows the current assembly's JSON boundary.
        selected = json.loads(messages[0].content.rsplit("\n", 1)[-1])
        return ModelReply(
            message=Message(
                role="assistant",
                content="离线脚本实际收到的项目约定：" + selected["text"].strip(),
            )
        )


if __name__ == "__main__":
    print("离线上下文观察：只读取本次创建的临时规则，不调用模型、不读取API Key。")
    print("本演示不执行编辑工具或测试工具，不需要输入yes。")
    with tempfile.TemporaryDirectory(prefix="herta-instructions-demo-") as folder:
        root = Path(folder)
        rules = root / "AGENTS.md"
        rules.write_text("- 解释改动时先说原因。\n", encoding="utf-8")
        agent = create_agent(
            InspectContextFixture(),
            RunSettings(),
            Repository(root),
            instructions="AGENTS.md",
        )
        session = Session()
        with asyncio.Runner() as runner:
            print("第一轮：")
            first = runner.run(run_turn(agent, session, "查看本轮约定"))
            print_result(first)
            rules.write_text("- 解释改动时给一个具体例子。\n", encoding="utf-8")
            print("演示脚本现在修改自己的临时规则文件；这不是模型自动学习。")
            print("第二轮：")
            second = runner.run(run_turn(agent, session, "再次查看约定"))
            print_result(second)
        print(
            "两轮上下文指纹是否变化：" + str(first.context_hash != second.context_hash)
        )
