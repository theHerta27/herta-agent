"""Local learning fixture using the same CLI assembly/loop, never a model service."""

import asyncio
import json
from pathlib import Path

from herta_agent.cli import chat, create_agent
from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.coding.paths import Repository

QUERY = "def add_tax"


class SearchReadFixture:
    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "user":
            return self.call(
                "find", "grep_code", {"query": QUERY, "path": "shop", "limit": 1}
            )
        feedback = json.loads(messages[-1].content)
        if not feedback["ok"]:
            return self.answer(f"固定脚本收到工具错误：{feedback['error']}")
        if messages[-1].tool_call_id == "find":
            print(
                "搜索工具实际返回：" + json.dumps(feedback["data"], ensure_ascii=False)
            )
            if not feedback["data"]["matches"]:
                return self.answer(
                    "未命中。工具执行成功，但没有找到这个区分大小写的字面关键词。"
                )
            hit = feedback["data"]["matches"][0]
            return self.call(
                "read",
                "read_file",
                {
                    "path": hit["path"],
                    "start_line": hit["line"],
                    "end_line": hit["line"] + 1,
                },
            )
        data = feedback["data"]
        lines = "\n".join(f"{row['line']}: {row['text']}" for row in data["lines"])
        return self.answer(f"固定脚本收到真实正文 {data['path']}：\n{lines}")

    @staticmethod
    def call(call_id, name, arguments):
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id=call_id,
                        name=name,
                        arguments=json.dumps(arguments, ensure_ascii=False),
                    ),
                ),
            )
        )

    @staticmethod
    def answer(text):
        return ModelReply(message=Message(role="assistant", content=text))


if __name__ == "__main__":
    print(f"离线学习夹具：固定搜索 {QUERY!r} 后读取；不调用真实模型，不读取API Key。")
    agent = create_agent(
        SearchReadFixture(), RunSettings(), Repository(Path(__file__).parent)
    )
    with asyncio.Runner() as runner:
        chat(agent, "找到add_tax并读取函数正文", runner)
