"""Transport-independent execution notifications; never a message history."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    type: Literal[
        "llm.started", "llm.delta", "llm.completed", "tool.started", "tool.completed", "tool.failed"
    ]
    step: int = Field(ge=1)
    message_id: str
    tool_call_id: str | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class EventSink(Protocol):
    async def emit(self, event: RuntimeEvent) -> None: ...


class NullSink:
    async def emit(self, event: RuntimeEvent) -> None:
        pass
