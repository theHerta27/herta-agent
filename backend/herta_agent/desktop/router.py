import base64

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from herta_agent.companion.speech_router import owned_request
from herta_agent.workspace.router import control_authorization


class Screenshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    png: str = Field(min_length=12, max_length=5_400_000)


def desktop_router(settings):
    router = APIRouter(prefix="/desktop", dependencies=[Depends(control_authorization(settings))])

    @router.post("/ocr")
    async def ocr(body: Screenshot, request: Request):
        try:
            data = base64.b64decode(body.png, validate=True)
        except ValueError:
            raise ValueError("截图编码无效。") from None
        return await owned_request(request, request.app.state.desktop.ocr(data))

    return router
