"""Generate the public local audio fixture used by desktop acceptance; no cloud calls."""

import asyncio
import io
import json
import wave
from pathlib import Path

import numpy as np
from herta_agent.companion.speech import SpeechService


async def main():
    root = Path(__file__).resolve().parents[1] / ".local"
    service = SpeechService()
    data = await service.synthesize("你好，我是黑塔。该休息了。")
    (root / "companion-voice-smoke.wav").write_bytes(data)
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
    if not result["text"].strip():
        raise RuntimeError("Local voice fixture was not recognized.")
    report = {"asr": result, "active_children": service.active_children}
    (root / "companion-voice-smoke.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())
