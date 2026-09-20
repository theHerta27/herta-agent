"""Context construction independent of the agent loop and persona storage."""

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from herta_agent.runtime.errors import ContextError
from herta_agent.runtime.messages import Message

DEFAULT_SYSTEM = "You are a helpful assistant. Answer clearly and accurately."


@dataclass(frozen=True)
class ContextSnapshot:
    """One immutable system text per Run; history is refreshed for each Step."""

    system_text: str
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.system_text.strip() or "\x00" in self.system_text:
            raise ContextError("System context 必须是非空有效文本。")
        object.__setattr__(
            self, "sha256", hashlib.sha256(self.system_text.encode("utf-8")).hexdigest()
        )

    def build_messages(self, history: tuple[Message, ...]) -> tuple[Message, ...]:
        if any(message.role == "system" for message in history):
            raise ContextError("会话历史不能包含 system 消息；由 Context Builder 统一注入。")
        return (Message(role="system", content=self.system_text), *history)


class ContextBuilder(Protocol):
    def snapshot(self) -> ContextSnapshot:
        """Load once at the start of a Run, or raise ContextError."""
        ...


@dataclass(frozen=True)
class StaticContextBuilder:
    """General runtime/test use only; never a fallback for failed persona loading."""

    system_text: str = DEFAULT_SYSTEM

    def snapshot(self) -> ContextSnapshot:
        return ContextSnapshot(self.system_text)
