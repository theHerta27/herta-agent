"""One offline model worker, with bounded idle reuse and owned cancellation."""

import asyncio
import io
import json
import os
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

from herta_agent.documents.process import attach_job

from .worker_process import resume_process


class HertaSpeech:
    def __init__(self, root, *, python=None, worker=None, idle_seconds=300):
        self.root = Path(root)
        self.python = python or self.root / ".venv/Scripts/python.exe"
        self.worker = worker or Path(__file__).resolve().parents[3] / "scripts/gpt_sovits/worker.py"
        self._slot = asyncio.Lock()
        self._closing = asyncio.Lock()
        self._lifecycle = asyncio.Lock()
        self._shutting_down = False
        self._child = None
        self._job = None
        self._draining = None
        self._idle = None
        self._warm = None
        self._active = 0
        self._epoch = 0
        self.idle_seconds = idle_seconds
        self.initializing = False
        self.loaded = False
        self.primed = False

    @property
    def active_children(self):
        return self._active

    @property
    def resident_children(self):
        return int(self._child is not None and self._child.returncode is None)

    def ready(self):
        return (
            self.python.is_file()
            and self.worker.is_file()
            and (self.root / "base-model-manifest.json").is_file()
        )

    def prewarm(self):
        if not self.ready() or self.loaded or (self._warm and not self._warm.done()):
            return

        async def prepare():
            try:
                await self.warmup()
            except (ValueError, OSError, TimeoutError):
                pass

        self._warm = asyncio.create_task(prepare())

    def _cancel_idle(self):
        if self._idle and self._idle is not asyncio.current_task():
            self._idle.cancel()

    def _schedule_idle(self):
        self._cancel_idle()

        async def expire():
            await asyncio.sleep(self.idle_seconds)
            async with self._slot:
                await self._dispose(graceful=True)

        self._idle = asyncio.create_task(expire())

    async def _start(self):
        if self._child and self._child.returncode is None and self.loaded:
            return self._child
        await self._dispose()
        self.root.mkdir(parents=True, exist_ok=True)
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "LOCALAPPDATA",
                "APPDATA",
            }
        }
        env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HERTA_VOICE_RUNTIME=str(self.root))
        self.initializing = True
        try:
            self._child = await asyncio.create_subprocess_exec(
                str(self.python),
                "-X",
                "utf8",
                str(self.worker),
                "--device",
                "cuda",
                cwd=self.root,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=65536,
                creationflags=0x08000004 if os.name == "nt" else 0,
            )
            child = self._child
            if os.name == "nt":
                self._job = attach_job(child, memory_limit=None)
                resume_process(child.pid)

            async def drain():
                while await child.stderr.read(8192):
                    pass

            self._draining = asyncio.create_task(drain())
            ready = json.loads(await child.stdout.readline())
            if ready.get("type") != "ready" or ready.get("protocol") != 1:
                raise ValueError("音色推理环境未就绪。")
            self.loaded = True
            return child
        finally:
            self.initializing = False

    async def _dispose(self, *, graceful=False):
        async def close():
            async with self._closing:
                child = self._child
                if not child:
                    return
                self.loaded = False
                self.primed = False
                if graceful and child.returncode is None:
                    try:
                        async with asyncio.timeout(2):
                            child.stdin.write(b'{"id":"stop","command":"shutdown"}\n')
                            await child.stdin.drain()
                            await child.stdout.readline()
                            await child.wait()
                    except (OSError, TimeoutError, ValueError):
                        pass
                if self._job:
                    api, job = self._job
                    api.CloseHandle(job)
                    self._job = None
                if child.returncode is None:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
                await child.wait()
                if self._draining:
                    await self._draining
                self._child = None
                self._draining = None

        cleanup = asyncio.create_task(close())
        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        cleanup.result()
        if cancelled:
            raise asyncio.CancelledError

    async def warmup(self):
        self._cancel_idle()
        try:
            async with asyncio.timeout(180), self._slot:
                try:
                    if self._shutting_down:
                        raise asyncio.CancelledError
                    child = await self._start()
                    if not self.primed:
                        self.initializing = True
                        try:
                            await self._render(child, "你好，今天一起学习。", "neutral")
                            self.primed = True
                        finally:
                            self.initializing = False
                    self._schedule_idle()
                except BaseException:
                    await self._dispose()
                    raise
        except asyncio.CancelledError:
            raise

    async def shutdown(self):
        async with self._lifecycle:
            self._shutting_down = True
            self._epoch += 1
            self._cancel_idle()
            try:
                if self._warm and not self._warm.done():
                    self._warm.cancel()
                    await asyncio.gather(self._warm, return_exceptions=True)
                await self._dispose()
                async with self._slot:
                    await self._dispose()
                if self._idle:
                    await asyncio.gather(self._idle, return_exceptions=True)
            finally:
                self._shutting_down = False

    async def _render(self, child, text, emotion):
        with tempfile.TemporaryDirectory(prefix="speech-", dir=self.root) as folder:
            try:
                output = Path(folder) / "speech.wav"
                request_id = uuid4().hex
                child.stdin.write(
                    (
                        json.dumps(
                            {
                                "id": request_id,
                                "text": text,
                                "emotion": emotion,
                                "output_path": str(output),
                            }
                        )
                        + "\n"
                    ).encode()
                )
                await child.stdin.drain()
                result = json.loads(await child.stdout.readline())
                if (
                    result.get("id") != request_id
                    or not result.get("ok")
                    or result.get("wav_path") != str(output)
                ):
                    raise ValueError("音色合成失败。")
                if not output.is_file() or output.stat().st_size > 12_000_000:
                    raise ValueError("合成声音大小无效。")
                data = output.read_bytes()
                with wave.open(io.BytesIO(data), "rb") as audio:
                    if audio.getparams()[:3] != (1, 2, 32000) or audio.getnframes() <= 0:
                        raise ValueError("合成声音格式无效。")
                return data
            except BaseException:
                await self._dispose()
                raise

    async def synthesize(self, text, emotion="neutral"):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000 or "\x00" in text:
            raise ValueError("大黑塔朗读每段需为1–1000字。")
        if emotion not in {"neutral", "happy", "sad", "angry", "surprised"}:
            raise ValueError("语音情绪无效。")
        epoch = self._epoch
        self._cancel_idle()
        self._active += 1
        try:
            async with asyncio.timeout(180), self._slot:
                try:
                    if epoch != self._epoch or self._shutting_down:
                        raise asyncio.CancelledError
                    child = await self._start()
                    data = await self._render(child, text, emotion)
                    self.primed = True
                    self._schedule_idle()
                    return data
                except BaseException:
                    await self._dispose()
                    raise
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ValueError("本机大黑塔合成失败，请重试或切换Piper。") from error
        finally:
            self._active -= 1
