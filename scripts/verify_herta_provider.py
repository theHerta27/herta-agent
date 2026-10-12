"""Real local provider acceptance; never invokes a chat/embedding provider."""
import asyncio
import hashlib
import io
import json
import sys
import wave
from pathlib import Path

from herta_agent.companion.herta_speech import HertaSpeech


async def main():
    root = Path(__file__).resolve().parent.parent
    service = HertaSpeech(root / ".local/gpt-sovits")
    data = await service.synthesize("你好，我是黑塔。我们先把今天的计划安排好。", "neutral")
    target = root / ".local/voice/the-herta-acceptance.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    with wave.open(io.BytesIO(data), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    report = {"bytes": len(data), "duration_seconds": duration,
              "sha256": hashlib.sha256(data).hexdigest(), "owned_children": service.active_children}
    print(json.dumps(report))
    if service.active_children:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
