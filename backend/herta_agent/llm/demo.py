"""Offline teaching provider. This is deterministic echo logic, NOT a language model."""

from herta_agent.runtime.messages import Message, ModelReply


class DemoProvider:
    async def complete(self, messages: tuple[Message, ...]) -> ModelReply:
        user_messages = [message for message in messages if message.role == "user"]
        text = f"[离线演示，第 {len(user_messages)} 轮] 收到：{user_messages[-1].content}"
        return ModelReply(message=Message(role="assistant", content=text))
