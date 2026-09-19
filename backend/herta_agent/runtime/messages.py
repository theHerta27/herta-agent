"""Only the text-message types needed by Phase 1; tool messages arrive in Phase 2."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class ModelReply(BaseModel):
    """The adapter has already checked finish_reason and rejected tool calls."""

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
