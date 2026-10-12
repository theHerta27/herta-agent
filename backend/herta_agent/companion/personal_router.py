from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from herta_agent.workspace.router import control_authorization


class PersonalAction(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    kind: Literal["persona", "voice", "memory", "skill", "draft", "from_task"]
    id: str | None = Field(default=None, max_length=64)
    revision: int = Field(default=1, ge=1)
    action: Literal["edit", "approve", "disable", "enable", "delete"] = "edit"
    text: str = Field(default="", max_length=6000)
    title: str = Field(default="", max_length=100)
    provider: Literal["piper", "the_herta"] = "piper"
    emotion: Literal["neutral", "happy", "sad", "angry", "surprised"] = "neutral"


def personal_router(settings):
    router = APIRouter(prefix="/personal", dependencies=[Depends(control_authorization(settings))])

    @router.get("")
    def snapshot(request: Request):
        result = request.app.state.companion.personal.snapshot()
        try:
            path = Path(settings.soul_path)
            result["base_persona"] = (
                path.read_text(encoding="utf-8-sig")[:6000] if path.stat().st_size < 32000 else ""
            )
        except (OSError, UnicodeError):
            result["base_persona"] = ""
        result["speech"] = request.app.state.speech.status()
        return result

    @router.post("")
    async def action(body: PersonalAction, request: Request):
        p = request.app.state.companion.personal
        if body.kind == "persona":
            return p.persona(body.text, body.revision)
        if body.kind == "voice":
            return await request.app.state.speech.change_voice(body.provider, body.emotion)
        if body.kind == "memory":
            return p.memory(body.id, body.revision, body.action, body.text)
        if body.kind == "draft":
            return p.propose_skill(body.title, body.text)
        if body.kind == "from_task":
            return p.from_task(body.id)
        return p.change_skill(
            body.id,
            body.revision,
            body.action,
            title=body.title or None,
            instructions=body.text or None,
        )

    return router
