from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Preferences(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    nickname: str = Field(default="", max_length=60)
    auto_read: bool = False
    allow_tools: bool = True
    quiet_start: int = Field(default=23, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)


class ReminderInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    due_at: str
    repeat: Literal["once", "daily", "weekly"] = "once"


class MemoryInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: str = Field(min_length=1, max_length=200)


class SnoozeInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    minutes: int = Field(default=10, ge=1, le=10080)
