from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Preferences(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    nickname: str = Field(default="", max_length=60)
    volume: int = Field(default=40, ge=0, le=100)
    auto_read: bool = False
    allow_tools: bool = True
    quiet_start: int = Field(default=23, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)


class ReminderInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    due_at: str
    repeat: Literal["once", "daily", "weekly"] = "once"


class MusicInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    action: Literal["play", "pause", "next", "previous", "volume", "stop"]
    track_id: str | None = None
    volume: int | None = Field(default=None, ge=0, le=100)


class PlaybackReport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    revision: int = Field(ge=0)
    actual: Literal["playing", "paused", "stopped", "error"]
    error: str = Field(default="", max_length=200)


class MemoryInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: str = Field(min_length=1, max_length=200)


class SnoozeInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    minutes: int = Field(default=10, ge=1, le=10080)


class ImportInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    paths: list[str] = Field(min_length=1, max_length=200)
