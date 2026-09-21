"""The runtime depends on this interface, never on HTTPX or a vendor SDK."""

from collections.abc import AsyncIterator
from typing import Protocol

from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.messages import Message, ModelReply


class LLMProvider(Protocol):
    async def complete(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> ModelReply:
        """Return a complete assistant message containing text or tool calls."""
        ...


class StreamingLLMProvider(Protocol):
    def stream(
        self, messages: tuple[Message, ...], *, tools: tuple[dict, ...] = ()
    ) -> AsyncIterator[TextDelta | ReplyCompleted]: ...
