import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from herta_agent.companion.speech import SpeechService


class SpeechText(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: str = Field(min_length=1, max_length=1500)


async def owned_request(request, operation):
    async def disconnected():
        while not await request.is_disconnected():  # noqa: ASYNC110 - HTTP disconnect has no Event API
            await asyncio.sleep(0.15)

    work = asyncio.create_task(operation)
    gone = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((work, gone), return_when=asyncio.FIRST_COMPLETED)
        if work not in done:
            raise HTTPException(499, "语音请求已取消。")
        return work.result()
    finally:
        work.cancel()
        gone.cancel()
        await asyncio.gather(work, gone, return_exceptions=True)


def speech_router():
    router = APIRouter(prefix="/companion/speech")
    service = SpeechService()

    @router.get("")
    async def status():
        return service.status()

    @router.post("/tts")
    async def synthesize(body: SpeechText, request: Request):
        try:
            data = await owned_request(request, service.synthesize(body.text))
        except ValueError:
            raise HTTPException(503, "本地朗读失败，请检查语音模型。") from None
        return Response(data, media_type="audio/wav")

    @router.post("/asr")
    async def transcribe(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 2_000_000:
                raise HTTPException(413, "录音超过大小限制。")
        try:
            return await owned_request(request, service.transcribe(bytes(data)))
        except ValueError:
            raise HTTPException(422, "录音格式或本地识别模型不可用。") from None

    return router
