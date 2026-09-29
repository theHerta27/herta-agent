"""Scripted provider only; actual coding tools, Python tests, service and SQLite."""

import json
import sys
from pathlib import Path

from herta_agent.llm.streaming import ReplyCompleted
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import backend_host  # noqa: E402


def call(identifier, name, **args):
    return ToolCall(id=identifier, name=name, arguments=json.dumps(args, ensure_ascii=False))


def patch(old, new):
    return (
        "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def value():\n"
        f"-    return {old}\n+    return {new}\n"
    )


class Provider:
    async def stream(self, messages, *, tools=()):
        user_index = max(i for i, m in enumerate(messages) if m.role == "user")
        text = messages[user_index].content
        results = [m for m in messages[user_index + 1 :] if m.role == "tool"]
        count = len(results)
        if text == "read":
            calls = (
                (
                    call("grep", "grep_code", query="def value"),
                    call("read", "read_file", path="calc.py"),
                    call("ls", "list_directory"),
                )
                if not results
                else ()
            )
            answer = "定义在 calc.py:1，读取已核对。"
        elif text == "change":
            if count == 0:
                calls = (
                    call(
                        "plan",
                        "propose_plan",
                        steps=[
                            {
                                "title": "核对函数和失败测试",
                                "rationale": "确认修改依据",
                            },
                            {
                                "title": "修复返回值并验证",
                                "rationale": "以测试结果判定",
                            },
                        ],
                    ),
                )
            elif count == 1:
                calls = (
                    call("read", "read_file", path="calc.py"),
                    call("before", "run_tests"),
                )
            elif count == 3:
                calls = (call("patch", "apply_patch", patch=patch(1, 2)),)
            elif count == 4:
                calls = (call("after", "run_tests"),)
            else:
                calls = ()
            answer = "副本修改后测试通过，原仓库保持不变。"
        elif text == "break":
            calls = (
                (call("patch", "apply_patch", patch=patch(2, 3)),)
                if count == 0
                else ((call("test", "run_tests"),) if count == 1 else ())
            )
            answer = "测试失败，没有将失败当作通过。"
        else:
            assert not {"apply_patch", "run_tests"} & {t["function"]["name"] for t in tools}
            if count == 0:
                calls = (call("read", "read_file", path="calc.py"),)
            elif count == 1:
                calls = (
                    call(
                        "review",
                        "submit_review",
                        findings=[
                            {
                                "category": "bug",
                                "title": "返回值违反测试约定",
                                "path": "calc.py",
                                "start_line": 2,
                                "end_line": 2,
                                "explanation": "当前返回 3，而测试要求 2。",
                            }
                        ],
                    ),
                )
            else:
                calls = ()
            answer = "只读评审完成，未修改代码。"
        yield ReplyCompleted(
            ModelReply(
                message=Message(
                    role="assistant",
                    tool_calls=calls,
                    content=None if calls else answer,
                )
            )
        )


backend_host.create_app = lambda settings: create_app(settings, provider=Provider())
backend_host.main()
