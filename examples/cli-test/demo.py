"""Deterministic fail → read → confirmed edit → pass through the same Agent Loop."""

import asyncio
import json
import tempfile
from pathlib import Path

from herta_agent.cli import chat, create_agent
from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.permissions import TerminalApproval


class TestEditFixture:
    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "user":
            return self.call("before", "run_tests", {"path": "tests"})
        feedback = json.loads(messages[-1].content)
        if not feedback["ok"]:
            return self.answer(
                "固定脚本收到工具错误："
                + json.dumps(feedback["error"], ensure_ascii=False)
            )
        call_id = messages[-1].tool_call_id
        data = feedback["data"]
        if call_id in ("before", "after"):
            print(
                f"真实测试结果：ok={feedback['ok']}，status={data['status']}，tests_run={data['tests_run']}"
            )
            print(data["output"])
            if call_id == "after" or data["status"] != "failed":
                return self.answer("固定脚本结束；最终真实测试状态：" + data["status"])
            return self.call("read", "read_file", {"path": "calculation.py"})
        if call_id == "read":
            return self.call(
                "edit",
                "edit_file",
                {
                    "path": "calculation.py",
                    "old_text": "return value + 2",
                    "new_text": "return value + 1",
                    "expected_sha256": data["sha256"],
                },
            )
        return self.call("after", "run_tests", {"path": "tests"})

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
    print("Windows离线固定脚本：测试失败→读取→确认编辑→再测通过；不调用模型。")
    print("只执行本次创建的临时演示代码，共需确认三次；任意一次拒绝就结束。")
    with tempfile.TemporaryDirectory(prefix="herta-test-demo-") as folder:
        root = Path(folder)
        (root / "tests").mkdir()
        target = root / "calculation.py"
        target.write_text(
            "def add_one(value):\n    return value + 2\n", encoding="utf-8"
        )
        (root / "tests/test_calculation.py").write_text(
            "import unittest\nfrom calculation import add_one\nclass CalculationTests(unittest.TestCase):\n    def test_add_one(self):\n        self.assertEqual(add_one(1), 2)\n",
            encoding="utf-8",
        )
        repo = Repository(root)
        with asyncio.Runner() as runner:
            chat(
                create_agent(
                    TestEditFixture(),
                    RunSettings(),
                    repo,
                    authorize=TerminalApproval(repo),
                ),
                "检查add_one，确认修复后重新测试。",
                runner,
            )
        print("结束时实际源码：\n" + target.read_text(encoding="utf-8"))
