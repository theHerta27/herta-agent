"""One in-memory conversation; no database or long-term memory in Phase 1.
负责当前这一次聊天状态。
"""

from dataclasses import dataclass, field
from uuid import uuid4

from herta_agent.runtime.errors import SessionBusyError
from herta_agent.runtime.messages import Message


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    context_hash: str | None = field(default=None, init=False)
    _messages: list[Message] = field(default_factory=list, init=False, repr=False)
    _busy: bool = field(default=False, init=False, repr=False)
    _pending: dict[str, None] = field(default_factory=dict, init=False, repr=False)

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
        if not self._busy or reply.role != "assistant" or reply.tool_calls or self._pending:
            raise ValueError("complete_turn requires an active turn and an assistant reply")
        self._messages.append(reply)

    def record_calls(self, reply: Message) -> None:
        if not self._busy or self._pending or reply.role != "assistant" or not reply.tool_calls:
            raise ValueError("Tool calls require an active turn without pending results")
        self._messages.append(reply)
        self._pending = dict.fromkeys(call.id for call in reply.tool_calls)

    def record_result(self, call_id: str, content: str) -> None:
        if not self._busy or call_id not in self._pending:
            raise ValueError("Tool result does not match a pending call")
        self._messages.append(Message(role="tool", content=content, tool_call_id=call_id))
        del self._pending[call_id]

    def close_pending(self, content: str) -> None:
        for call_id in tuple(self._pending):
            self.record_result(call_id, content)

    def end_turn(self) -> None:
        self._busy = False
