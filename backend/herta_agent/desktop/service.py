"""Owned local OCR, sharing only images explicitly submitted by the user."""

import asyncio
import base64
import io
import threading

from herta_agent.documents.process import run_document
from herta_agent.workspace.paths import WorkspaceError


def validate_image(data):
    from PIL import Image

    if (
        not isinstance(data, bytes)
        or not 8 <= len(data) <= 4_000_000
        or (not data.startswith(b"\x89PNG\r\n\x1a\n"))
    ):
        raise WorkspaceError("截图需为不超过4MB的PNG。")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 4_000_000:
                raise WorkspaceError("截图像素过大，请缩小窗口后重试。")
            image.verify()
    except (OSError, ValueError) as error:
        raise WorkspaceError("截图格式不完整。") from error


class DesktopService:
    def __init__(self):
        self.tasks = {}
        self.closing = False

    @property
    def active_count(self):
        return len(self.tasks)

    async def ocr(self, data):
        validate_image(data)
        if self.closing or self.tasks:
            raise WorkspaceError("已有截图正在识别，请等待或停止。")
        stop = threading.Event()
        request = {
            "kind": "ocr",
            "files": [{"suffix": ".png", "data": base64.b64encode(data).decode()}],
        }
        work = asyncio.create_task(asyncio.to_thread(run_document, request, stop))
        self.tasks[work] = stop
        try:
            return await asyncio.shield(work)
        finally:
            stop.set()
            while not work.done():
                try:
                    await asyncio.shield(work)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            self.tasks.pop(work, None)

    async def shutdown(self):
        self.closing = True
        for stop in tuple(self.tasks.values()):
            stop.set()
        await asyncio.gather(*(asyncio.shield(t) for t in self.tasks), return_exceptions=True)
