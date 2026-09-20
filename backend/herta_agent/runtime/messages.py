"""Immutable internal messages with explicit Chat Completions encoding."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ToolCall(BaseModel):
    """Arguments remain raw JSON until the executor validates the registered schema."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=256, pattern=r"\S")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    arguments: str

    def to_wire(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


class Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def validate_role(self) -> "Message":
        if self.tool_calls:
            if self.role != "assistant":
                raise ValueError("Only assistant messages can call tools")
            ids = [call.id for call in self.tool_calls]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate tool call id")
        elif self.content is None or not self.content.strip():
            raise ValueError("消息内容不能为空")
        if self.role == "tool":
            if not self.tool_call_id or not self.tool_call_id.strip():
                raise ValueError("Tool result requires a call id")
        elif self.tool_call_id is not None:
            raise ValueError("Only tool results can contain tool_call_id")
        return self

    def to_wire(self) -> dict:
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [call.to_wire() for call in self.tool_calls]
        if self.role == "tool":
            result["tool_call_id"] = self.tool_call_id
        return result


class ModelReply(BaseModel):
    """The adapter has checked finish_reason and normalized any tool calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: Message

    @field_validator("message")
    @classmethod
    def require_assistant(cls, value: Message) -> Message:
        if value.role != "assistant":
            raise ValueError("模型回复必须为 assistant 消息")
        return value


class RunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    reply: str
    steps: int
    context_hash: str | None = None
