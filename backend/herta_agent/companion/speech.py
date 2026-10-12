"""Bounded, owned local voice processes. There is no remote fallback."""

import asyncio
import importlib.util
import io
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

VOICE_ROOT = Path(__file__).resolve().parents[3] / ".local" / "voice"


def validate_audio(data: bytes):
    if len(data) > 2_000_000:
        raise ValueError("录音超过大小限制。")
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if audio.getparams()[:3] != (1, 2, 16000) or not 0 < audio.getnframes() <= 960000:
                raise ValueError("录音需为16kHz单声道PCM，最长60秒。")
            if len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2:
                raise ValueError("录音数据不完整。")
            return audio.getnframes() / 16000
    except (wave.Error, EOFError):
        raise ValueError("录音格式无效。") from None


class SpeechService:
    def __init__(self, root=VOICE_ROOT, *, personal=None):
        self.root = root
        self.personal = personal
        from herta_agent.companion.herta_speech import HertaSpeech

        self.herta = HertaSpeech(VOICE_ROOT.parent / "gpt-sovits")
        self._children = set()
        self._slot = asyncio.Semaphore(1)

    @property
    def active_children(self):
        return len(self._children) + self.herta.active_children

    def status(self):
        tts = bool(importlib.util.find_spec("piper")) and all(
            (self.root / name).is_file()
            for name in ("zh_CN-huayan-medium.onnx", "zh_CN-huayan-medium.onnx.json")
        )
        asr = bool(importlib.util.find_spec("faster_whisper")) and all(
            (self.root / "asr" / name).is_file()
            for name in ("model.bin", "config.json", "tokenizer.json")
        )
        choice = self.personal.snapshot()["voice"] if self.personal else {"provider": "piper"}
        selected = choice["provider"]
        ready = tts if selected == "piper" else self.herta.ready()
        return {
            "tts": ready,
            "asr": asr,
            "active_workers": self.active_children,
            "provider": selected,
            "providers": {"piper": tts, "the_herta": self.herta.ready()},
            "detail": (
                "大黑塔音色就绪 · 首段需要加载模型"
                if selected == "the_herta"
                else "Piper本地语音就绪"
            )
            if ready
            else "运行语音准备脚本或切换已准备的音色。",
        }

    async def shutdown(self):
        for child in tuple(self._children):
            if child.returncode is None:
                child.kill()
            await child.wait()
        await self.herta.shutdown()

    async def run_worker(self, command, data):
        async with self._slot:
            env = {**os.environ, "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1"}
            child = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._children.add(child)
            try:
                async with asyncio.timeout(120):
                    output, _ = await child.communicate(data)
                if child.returncode != 0 or len(output) > 12_000_000:
                    raise ValueError("本地语音处理失败，请核对模型和依赖。")
                return output
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
                self._children.discard(child)

    async def synthesize(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 1500 or "\x00" in text:
            raise ValueError("朗读内容需为1–1500字。")
        if not self.status()["tts"]:
            raise ValueError("本地朗读模型未准备。")
        if self.personal and self.personal.snapshot()["voice"]["provider"] == "the_herta":
            return await self.herta.synthesize(text, self.personal.snapshot()["voice"]["emotion"])
        return await self.run_worker(
            [sys.executable, "-m", "herta_agent.companion.speech_worker", "tts", str(self.root)],
            text.encode("utf-8"),
        )

    async def transcribe(self, data):
        validate_audio(data)
        with wave.open(io.BytesIO(data), "rb") as audio:
            pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(
                np.float32
            )
        if np.max(np.abs(pcm)) < 128:
            return {"text": ""}
        if not self.status()["asr"]:
            raise ValueError("本地识别模型未准备。")
        output = await self.run_worker(
            [sys.executable, "-m", "herta_agent.companion.speech_worker", "asr", str(self.root)],
            data,
        )
        return json.loads(output)
