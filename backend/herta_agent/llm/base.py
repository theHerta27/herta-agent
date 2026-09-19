"""The runtime depends on this interface, never on HTTPX or a vendor SDK."""

from typing import Protocol

from herta_agent.runtime.messages import Message, ModelReply


class LLMProvider(Protocol):
    async def complete(self, messages: tuple[Message, ...]) -> ModelReply:
        """Return a complete text reply, or raise an expected Provider/Agent error."""
        ...
