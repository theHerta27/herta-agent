"""Explicitly registered daily tools; identity grants cannot bless arbitrary MCP tools."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field

from herta_agent.companion.store import CompanionStore, instant
from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.registry import ToolParameters, ToolSpec


class ReminderParameters(ToolParameters):
    title: str = Field(min_length=1, max_length=200)
    delay_minutes: int | None = Field(default=None, ge=1, le=10080)
    due_at: str | None = None
    repeat: Literal["once", "daily", "weekly"] = "once"


class Identifier(ToolParameters):
    id: str = Field(min_length=1, max_length=64)


class MemoryParameters(ToolParameters):
    text: str = Field(min_length=1, max_length=200)


def companion_tools(store: CompanionStore):
    async def create(args):
        if (args.delay_minutes is None) == (args.due_at is None):
            raise ToolExecutionError("invalid_arguments", "delay_minutes和带时区due_at必须二选一。")
        now = datetime.now(UTC)
        try:
            due = (
                now + timedelta(minutes=args.delay_minutes)
                if args.delay_minutes
                else instant(args.due_at)
            )
            if not now < due <= now + timedelta(days=730):
                raise ValueError("提醒必须在未来两年内。")
            return store.create_reminder(args.title, due.isoformat(), args.repeat)
        except ValueError as error:
            raise ToolExecutionError("invalid_arguments", str(error)) from None

    async def list_reminders(_):
        return store.snapshot()["reminders"][:50]

    async def cancel(args):
        store.cancel_reminder(args.id)
        return {"cancelled": args.id}

    async def propose(args):
        return {
            "candidate": store.propose_memory(args.text, source="chat_proposal"),
            "note": "待用户在日常面板确认保存，尚未进入长期记忆。",
        }

    specs = (
        ToolSpec(
            "create_reminder",
            "创建用户要求的提醒。相对分钟或含时区ISO时间二选一；只在用户明确要求提醒时使用。",
            ReminderParameters,
            create,
            permission="side_effect",
        ),
        ToolSpec("list_reminders", "查看本机提醒及准确时间。", ToolParameters, list_reminders),
        ToolSpec(
            "cancel_reminder",
            "取消用户指定ID的提醒；先查询提醒列表确定ID。",
            Identifier,
            cancel,
            permission="side_effect",
        ),
        ToolSpec(
            "propose_memory",
            "根据用户明确要求或纠正提出一条待确认记忆；用户保存后才成为长期记忆。",
            MemoryParameters,
            propose,
            permission="side_effect",
        ),
    )

    def policy(spec):
        return (
            any(spec is trusted for trusted in specs)
            and store.snapshot()["preferences"]["allow_tools"]
        )

    return specs, policy
