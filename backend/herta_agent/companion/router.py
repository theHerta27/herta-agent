import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from herta_agent.companion.models import (
    ImportInput,
    MemoryInput,
    MusicInput,
    PlaybackReport,
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

    @router.post("/music/import")
    async def import_music(body: ImportInput, request: Request):
        return request.app.state.companion.import_tracks(body.paths)

    @router.post("/music/control")
    async def control(body: MusicInput, request: Request):
        return request.app.state.companion.music_command(body.action, body.track_id, body.volume)

    @router.post("/music/report")
    async def report(body: PlaybackReport, request: Request):
        request.app.state.companion.report_playback(body.revision, body.actual, body.error)
        return {"ok": True}

    @router.get("/music/media/{identifier}")
    async def media(identifier: str, request: Request):
        try:
            path = request.app.state.companion.media_path(identifier)
        except (ValueError, OSError):
            return JSONResponse(
                {"error": {"code": "media_unavailable", "message": "音乐文件不可用，请重新导入。"}},
                status_code=404,
            )
        return FileResponse(path)

    return router
