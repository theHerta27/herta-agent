"""A temporary-file edit lesson using the production CLI assembly and approval."""

import asyncio
import json
import tempfile
from pathlib import Path

from herta_agent.cli import chat, create_agent
from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval

OLD_TEXT = "value = 1"
NEW_TEXT = "value = 2"


class EditFixture:
    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "user":
            return self.call("initial", "read_file", {"path": "note.py"})
        feedback = json.loads(messages[-1].content)
        if not feedback["ok"]:
            return self.answer(
                "固定脚本收到工具错误："
                + json.dumps(feedback["error"], ensure_ascii=False)
            )
        if messages[-1].tool_call_id == "initial":
            return self.call(
                "edit",
                "edit_file",
                {
                    "path": "note.py",
                    "old_text": OLD_TEXT,
                    "new_text": NEW_TEXT,
                    "expected_sha256": feedback["data"]["sha256"],
                },
            )
        if messages[-1].tool_call_id == "edit":
            print("实际写入收据：" + json.dumps(feedback["data"], ensure_ascii=False))
            return self.call("verify", "read_file", {"path": "note.py"})
        data = feedback["data"]
        lines = "\n".join(f"{row['line']}: {row['text']}" for row in data["lines"])
        return self.answer(f"固定脚本收到回读正文：\n{lines}\nsha256={data['sha256']}")

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
    print("离线固定脚本：Read→确认Edit→Read，不调用模型、不读取API Key。")
    print("只修改本次创建的临时演示文件；结束时自动清理。")
    with tempfile.TemporaryDirectory(prefix="herta-edit-demo-") as folder:
        root = Path(folder)
        target = root / "note.py"
        target.write_bytes(b"value = 1\nuntouched = True\n")
        repo = Repository(root)
        agent = create_agent(
            EditFixture(), RunSettings(), repo, authorize=TerminalApproval(repo)
        )
        with asyncio.Runner() as runner:
            chat(agent, "把value从1改成2，先确认差异，再读取核对。", runner)
        print("演示结束时的实际文件：\n" + target.read_text(encoding="utf-8"))
