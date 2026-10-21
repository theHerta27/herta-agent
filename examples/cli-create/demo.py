"""Fixed create → approve → read sequence, using only a disposable project."""

import asyncio
import json
import tempfile
from pathlib import Path

from herta_agent.cli import chat, create_agent
from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


class CreateReadFixture:
    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "user":
            return self.call(
                "create",
                "create_file",
                {"path": "answer.py", "content": "answer = 42\n"},
            )
        feedback = json.loads(messages[-1].content)
        if not feedback["ok"]:
            return self.answer(
                "固定脚本收到工具错误："
                + json.dumps(feedback["error"], ensure_ascii=False)
            )
        if messages[-1].tool_call_id == "create":
            print("实际创建收据：" + json.dumps(feedback["data"], ensure_ascii=False))
            return self.call("read", "read_file", {"path": "answer.py"})
        return self.answer(
            "固定脚本收到回读结果：" + json.dumps(feedback["data"], ensure_ascii=False)
        )

    @staticmethod
    def call(call_id, name, arguments):
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(
                    ToolCall(id=call_id, name=name, arguments=json.dumps(arguments)),
                ),
            )
        )

    @staticmethod
    def answer(text):
        return ModelReply(message=Message(role="assistant", content=text))


if __name__ == "__main__":
    print("离线固定脚本：确认新建→实际创建→回读；不调用模型，不读取API Key。")
    print("只在本次临时项目创建answer.py，不执行其代码；结束自动清理。")
    with tempfile.TemporaryDirectory(prefix="herta-create-demo-") as folder:
        repo = Repository(Path(folder))
        with asyncio.Runner() as runner:
            chat(
                create_agent(
                    CreateReadFixture(),
                    RunSettings(),
                    repo,
                    authorize=TerminalApproval(repo),
                ),
                "创建answer.py并回读核对。",
                runner,
            )
        target = repo.root / "answer.py"
        print(
            "结束时实际文件："
            + (target.read_text(encoding="utf-8") if target.exists() else "不存在")
        )
