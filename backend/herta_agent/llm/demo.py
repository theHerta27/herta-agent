"""Offline teaching provider. This is deterministic echo logic, NOT a language model."""

import json
from uuid import uuid4

from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.tools.echo import EchoParameters


class DemoProvider:
    async def complete(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> ModelReply:
        user_messages = [message for message in messages if message.role == "user"]
        text = f"[离线演示，第 {len(user_messages)} 轮] 收到：{user_messages[-1].content}"
        return ModelReply(message=Message(role="assistant", content=text))


class ToolDemoProvider:
    """Deterministic calls exercise the same loop and executor as a real provider."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = EchoParameters(
            text="validate", delay_seconds=delay_seconds
        ).delay_seconds

    async def complete(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> ModelReply:
        if messages[-1].role == "tool":
            return ModelReply(
                message=Message(
                    role="assistant", content=f"[离线工具演示] 工具结果：{messages[-1].content}"
                )
            )
        text = next(message.content for message in reversed(messages) if message.role == "user")
        arguments = json.dumps(
            {"text": text, "delay_seconds": self.delay_seconds}, ensure_ascii=False
        )
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(ToolCall(id=f"demo_{uuid4().hex}", name="echo", arguments=arguments),),
            )
        )


class ReadDemoProvider:
    """Fixed read_file call, then display real feedback; no natural-language routing."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def complete(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> ModelReply:
        if messages[-1].role == "tool":
            return ModelReply(
                message=Message(
                    role="assistant", content=f"[离线读文件演示] 工具结果：{messages[-1].content}"
                )
            )
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id=f"read_{uuid4().hex}",
                        name="read_file",
                        arguments=json.dumps({"path": self.path}, ensure_ascii=False),
                    ),
                ),
            )
        )
