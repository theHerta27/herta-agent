"""One in-memory conversation; no database or long-term memory in Phase 1."""

from dataclasses import dataclass, field
from uuid import uuid4

from herta_agent.runtime.errors import SessionBusyError
from herta_agent.runtime.messages import Message


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    _messages: list[Message] = field(default_factory=list, init=False, repr=False)
    _busy: bool = field(default=False, init=False, repr=False)

    @property
    def history(self) -> tuple[Message, ...]:
        """Return an immutable snapshot, not the mutable internal list."""
        return tuple(self._messages)

    def begin_turn(self, user_message: Message) -> None:
        # This synchronous section contains no await: admission is atomic on one event loop.
        if self._busy:
            raise SessionBusyError("这个会话正在执行，请等待完成或先取消。")
        if user_message.role != "user":
            raise ValueError("begin_turn requires a user message")
        self._messages.append(user_message)
        self._busy = True

    def complete_turn(self, reply: Message) -> None:
        if not self._busy or reply.role != "assistant":
            raise ValueError("complete_turn requires an active turn and an assistant reply")
        self._messages.append(reply)

    def end_turn(self) -> None:
        self._busy = False
