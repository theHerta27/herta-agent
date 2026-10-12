import asyncio
import ctypes
import io
import os
import sys
import tempfile
import unittest
import wave
from ctypes import wintypes
from pathlib import Path

import numpy as np

from herta_agent.companion.speech import SpeechService, validate_audio


def wav(seconds=1, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(bytes(seconds * rate * 2))
    return output.getvalue()


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_switch_blocks_new_request_admission_until_new_provider_is_saved(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from herta_agent.companion.personal_router import PersonalAction, personal_router
        from herta_agent.companion.store import CompanionStore
        from herta_agent.service.settings import ServiceSettings

        with tempfile.TemporaryDirectory() as folder:
            daily = CompanionStore(Path(folder) / "companion.sqlite3")
            daily.personal.voice("piper", "neutral")
            service = SpeechService(personal=daily.personal)
            closing, release_close, release_old = asyncio.Event(), asyncio.Event(), asyncio.Event()
            old_started = False

            async def close():
                closing.set()
                await release_close.wait()

            async def old_worker(*_args):
                nonlocal old_started
                old_started = True
                await release_old.wait()
                return b"old provider"

            service.status = lambda: {"tts": True}
            service.run_worker = old_worker
            service.herta.shutdown = close
            service.herta.prewarm = lambda: None
            service.herta.synthesize = AsyncMock(return_value=b"new provider")
            route = next(
                r for r in personal_router(ServiceSettings()).routes if "POST" in r.methods
            )
            request = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(speech=service, companion=daily))
            )
            switch = asyncio.create_task(
                route.endpoint(PersonalAction(kind="voice", provider="the_herta"), request)
            )
            voice = None
            try:
                await closing.wait()
                voice = asyncio.create_task(service.synthesize("新的朗读"))
                await asyncio.sleep(0.03)
                started_before_switch = old_started
                release_close.set()
                release_old.set()
                await switch
                self.assertEqual(await voice, b"new provider")
                self.assertFalse(started_before_switch, "切换过程中不能让新请求启动旧音色")
            finally:
                release_close.set()
                release_old.set()
                await asyncio.gather(switch, *([voice] if voice else []), return_exceptions=True)
                await service.shutdown()

    async def test_invalid_audio_and_duration_are_rejected_before_provider(self):
        for invalid in (b"not audio", wav(61), wav(rate=8000), bytes(2_000_001)):
            with self.assertRaises(ValueError):
                validate_audio(invalid)
        self.assertEqual(validate_audio(wav()), 1)

    async def test_absent_models_report_unavailable_without_network_download(self):
        with tempfile.TemporaryDirectory() as folder:
            service = SpeechService(Path(folder))
            self.assertFalse(service.status()["asr"])
            self.assertFalse(service.status()["tts"])
            with self.assertRaises(ValueError):
                await service.synthesize("你好")
            self.assertEqual(await service.transcribe(wav()), {"text": ""})

    async def test_cancelling_owned_worker_terminates_actual_child(self):
        service = SpeechService(Path("unused"))
        task = asyncio.create_task(
            service.run_worker([sys.executable, "-c", "import time; time.sleep(60)"], b"")
        )
        await asyncio.sleep(0.4)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(service.active_children, 0)

    @unittest.skipUnless(os.name == "nt", "Windows venv launcher contract")
    async def test_cancel_terminates_actual_interpreter_not_only_venv_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pid"
            code = (
                "import os,time; from pathlib import Path; "
                f"Path({str(path)!r}).write_text(str(os.getpid())); time.sleep(60)"
            )
            service = SpeechService(Path(folder))
            task = asyncio.create_task(service.run_worker([sys.executable, "-c", code], b""))
            for _ in range(100):
                if path.exists():
                    break
                await asyncio.sleep(0.03)
            self.assertTrue(path.exists())
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            handle = kernel.OpenProcess(0x1000 | 1, False, int(path.read_text()))
            self.assertTrue(handle)
            try:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                kernel.WaitForSingleObject(handle, 3000)
                result = wintypes.DWORD()
                self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(result)))
                self.assertNotEqual(result.value, 259, "real interpreter was orphaned")
            finally:
                kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)

    async def test_local_provider_accepts_validated_pcm_without_pyav_codec_dependency(self):
        service = SpeechService()
        if not all(service.status()[key] for key in ("tts", "asr")):
            self.skipTest("local voice models are optional")
        data = await service.synthesize("你好，我是黑塔。该休息了。")
        with wave.open(io.BytesIO(data), "rb") as audio:
            rate = audio.getframerate()
            values = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        samples = np.interp(
            np.arange(int(len(values) * 16000 / rate)) * rate / 16000,
            np.arange(len(values)),
            values,
        ).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            audio.writeframes(samples.tobytes())
        result = await service.transcribe(buffer.getvalue())
        self.assertTrue(result["text"].strip())
        self.assertEqual(service.active_children, 0)


if __name__ == "__main__":
    unittest.main()
