"""Awaitable commit boundary; the Agent does not know how facts are stored."""

from typing import Protocol

from herta_agent.runtime.messages import Message
from herta_agent.runtime.session import Session
from herta_agent.tools.executor import ToolResult


class TurnIO(Protocol):
    async def begin(self, user: Message) -> None: ...
    async def set_context(self, context_hash: str) -> None: ...
    async def append(self, message: Message, *, message_id: str, step: int) -> None: ...
    async def complete(self, message: Message, *, message_id: str, step: int) -> None: ...
    async def abort(
        self, *, cancelled: bool, error_code: str, safe_message: str, step: int
    ) -> None: ...


class MemoryTurn:
    def __init__(self, session: Session):
        self.session = session

    async def begin(self, user: Message) -> None:
        self.session.begin_turn(user)
        self.session.context_hash = None

    async def set_context(self, context_hash: str) -> None:
        self.session.context_hash = context_hash

    async def append(self, message: Message, *, message_id: str, step: int) -> None:
        if message.role == "assistant":
            self.session.record_calls(message)
        elif message.role == "tool":
            self.session.record_result(message.tool_call_id, message.content)
        else:
            raise ValueError("Only assistant calls and tool results may be appended")

    async def complete(self, message: Message, *, message_id: str, step: int) -> None:
        self.session.complete_turn(message)

    async def abort(
        self, *, cancelled: bool, error_code: str, safe_message: str, step: int
    ) -> None:
        self.session.close_pending(ToolResult.failure(error_code, safe_message).to_json())
