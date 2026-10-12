from typing import Literal

from pydantic import Field

from herta_agent.tools.registry import ToolParameters


class TaskInput(ToolParameters):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    due_at: str | None = Field(default=None, max_length=64)
    repeat: Literal["once", "daily", "weekly"] = "once"
    remind: bool = False
    goal_id: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=64)


class GoalInput(ToolParameters):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    deadline: str | None = Field(default=None, max_length=64)


class MaterialInput(ToolParameters):
    title: str = Field(min_length=1, max_length=200)
    root_id: str | None = Field(default=None, max_length=64)
    path: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=2000)


class TaskChange(ToolParameters):
    action: Literal["complete", "postpone", "cancel", "reopen", "edit"]
    revision: int = Field(ge=1)
    due_at: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class MaterialChange(ToolParameters):
    revision: int = Field(ge=1)
    progress: int = Field(ge=0, le=100)
    notes: str = Field(default="", max_length=2000)


class Revision(ToolParameters):
    revision: int = Field(ge=1)


class GoalChange(Revision):
    status: Literal["active", "completed", "cancelled"]


class RoleInput(ToolParameters):
    role: Literal["default", "tutor", "interviewer", "recite", "review"]


class RecitationInput(ToolParameters):
    expected: str = Field(min_length=1, max_length=2000)
    transcript: str = Field(min_length=1, max_length=2000)
