"""Offline streaming fixture using the real service, runtime, tools and SQLite."""

import asyncio
import os
import sys
from pathlib import Path

from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service import app as service

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
import backend_host  # noqa: E402

ROOT = Path(os.environ["HERTA_FIXTURE_GATE"])


async def gate(name):
    (ROOT / (name + "-entered")).touch()
    while not (ROOT / (name + "-release")).exists():  # noqa: ASYNC110 - cross-process test gate
        await asyncio.sleep(0.02)


class Provider:
    async def stream(self, messages, *, tools=()):
        text = next(m.content for m in reversed(messages) if m.role == "user")
        if text == "tools" and messages[-1].role != "tool":
            yield ReplyCompleted(
                ModelReply(
                    message=Message(
                        role="assistant",
                        content="先查阅角色资料。",
                        tool_calls=(
                            ToolCall(id="echo", name="echo", arguments='{"text":"检查工具"}'),
                            ToolCall(
                                id="rag", name="search_knowledge", arguments='{"query":"黑塔"}'
                            ),
                        ),
                    )
                )
            )
            return
        if text == "stream":
            first, last = "正在生成，黑塔", "的完整回答。"
            yield TextDelta(first)
            await gate("stream")
        elif text == "cancel":
            yield TextDelta("未提交的半截回答")
            await asyncio.Event().wait()
            return
        else:
            first = "根据资料，" if text == "tools" else "你好，"
            last = "这是离线工具回答 [fixture-1]。" if text == "tools" else "这是离线回答。"
            yield TextDelta(first)
            await asyncio.sleep(0.15)
        yield TextDelta(last)
        yield ReplyCompleted(ModelReply(message=Message(role="assistant", content=first + last)))


class Retriever:
    async def search(self, query):
        await gate("tool")
        return {
            "query": query,
            "index_id": "offline-fixture",
            "chunks": [
                {
                    "id": "fixture-1",
                    "source": "角色资料.md",
                    "source_spans": [{"start_line": 1, "end_line": 3}],
                    "score": 0.9,
                    "text": "离线测试证据，不用于验证真实检索质量。",
                }
            ],
        }


original_spec = service.search_knowledge_spec
service.search_knowledge_spec = lambda **_: original_spec(Retriever())
backend_host.create_app = lambda settings: service.create_app(settings, provider=Provider())

if __name__ == "__main__":
    backend_host.main()
