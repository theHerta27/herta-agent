"""Opt-in local-model coverage, never a remote model evaluation."""

import io
import json
import os
import time
import unittest
import wave
from pathlib import Path

import numpy as np

from herta_agent.companion.herta_speech import HertaSpeech
from herta_agent.companion.speech import SpeechService

PROJECT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("HERTA_RUN_LOCAL_VOICE_ACCEPTANCE") == "1", "opt-in GPU model")
class HertaVoiceAcceptance(unittest.IsolatedAsyncioTestCase):
    async def test_short_first_sentence_keeps_the_following_sentence(self):
        root = PROJECT
        voice = HertaSpeech(root / ".local/gpt-sovits")
        asr = SpeechService(root / ".local/voice")
        try:
            started = time.perf_counter()
            data = await voice.synthesize("来了？今天想弄清什么。")
            elapsed = time.perf_counter() - started
            with wave.open(io.BytesIO(data), "rb") as source:
                frames = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
            pcm = io.BytesIO()
            with wave.open(pcm, "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(16000)
                target.writeframes(frames[::2].tobytes())
            result = await asr.transcribe(pcm.getvalue())
            evidence = root / ".local/voice-latency"
            evidence.mkdir(exist_ok=True)
            (evidence / "coverage.wav").write_bytes(data)
            (evidence / "coverage.json").write_text(
                json.dumps(
                    {"text": result["text"], "elapsed": elapsed, "bytes": len(data)},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            for word in ("今天", "弄", "清", "什"):
                self.assertIn(word, result["text"], "不能只合成第一声就返回成功")
        finally:
            await voice.shutdown()
            await asr.shutdown()
