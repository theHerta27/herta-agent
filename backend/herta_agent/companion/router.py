import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request

from herta_agent.companion.models import (
    MemoryInput,
    Preferences,
    ReminderInput,
    SnoozeInput,
)
from herta_agent.companion.store import instant


async def scheduler(store):
    while True:
        await asyncio.to_thread(store.tick)
        await asyncio.sleep(1)


async def stop_scheduler(task):
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def companion_router():
    router = APIRouter(prefix="/companion")

    @router.get("")
    async def snapshot(request: Request):
        return request.app.state.companion.snapshot()

    @router.put("/preferences")
    async def preferences(body: Preferences, request: Request):
        return request.app.state.companion.update_preferences(body.model_dump())

    @router.post("/reminders", status_code=201)
    async def create(body: ReminderInput, request: Request):
        now = datetime.now(UTC)
        if not now < instant(body.due_at) <= now + timedelta(days=730):
            raise ValueError("提醒必须在未来两年内。")
        return request.app.state.companion.create_reminder(body.title, body.due_at, body.repeat)

    @router.post("/reminders/{identifier}/cancel")
    async def cancel(identifier: str, request: Request):
        request.app.state.companion.cancel_reminder(identifier)
        return {"ok": True}

    @router.post("/reminders/{identifier}/snooze")
    async def snooze(identifier: str, body: SnoozeInput, request: Request):
        request.app.state.companion.snooze(identifier, body.minutes)
        return {"ok": True}

    @router.post("/deliveries/{identifier}/ack")
    async def acknowledge(identifier: str, request: Request):
        request.app.state.companion.acknowledge(identifier)
        return {"ok": True}

    @router.post("/deliveries/{identifier}/notified")
    async def notified(identifier: str, request: Request):
        request.app.state.companion.mark_notified(identifier)
        return {"ok": True}

    @router.post("/memories", status_code=201)
    async def memory(body: MemoryInput, request: Request):
        return request.app.state.companion.propose_memory(body.text)

    @router.post("/memories/{identifier}/approve")
    async def approve(identifier: str, request: Request):
        request.app.state.companion.approve_memory(identifier)
        return {"ok": True}

    @router.delete("/memories/{identifier}")
    async def delete(identifier: str, request: Request):
        request.app.state.companion.delete_memory(identifier)
        return {"ok": True}

    return router
