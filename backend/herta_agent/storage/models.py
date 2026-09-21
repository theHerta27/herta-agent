"""Immutable persisted facts. No event/partial records or credential configuration."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from herta_agent.config import RunSettings
from herta_agent.runtime.messages import Message

Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"\S")]
RunStatus = Literal["created", "running", "completed", "failed", "cancelled", "interrupted"]


class StoreError(Exception):
    """Safe error only: never include SQL, parameters or the underlying exception."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Record(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class RunConfig(Record):
    model: str = Field(min_length=1, max_length=256, pattern=r"\S")
    settings: RunSettings = Field(default_factory=RunSettings)


class SessionRecord(Record):
    session_id: Identifier
    created_at: str
    updated_at: str


class RunRecord(Record):
    run_id: Identifier
    session_id: Identifier
    status: RunStatus
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    steps: int = Field(default=0, ge=0, le=100)
    context_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config: RunConfig
    error: str | None = None


class MessageRecord(Record):
    message_id: Identifier
    session_id: Identifier
    run_id: Identifier
    seq: int = Field(ge=1)
    step: int = Field(ge=0, le=100)
    message: Message


class Admission(Record):
    run: RunRecord
    user: MessageRecord
