"""One-request local provider worker, terminated by its HTTP request owner on cancel."""

import io
import json
import sys
import wave
from pathlib import Path


def main():
    mode, root = sys.argv[1], Path(sys.argv[2])
    data = sys.stdin.buffer.read(2_000_001)
    if mode == "tts":
        from piper import PiperVoice

        voice = PiperVoice.load(root / "zh_CN-huayan-medium.onnx")
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            voice.synthesize_wav(data.decode("utf-8"), audio)
        sys.stdout.buffer.write(output.getvalue())
    elif mode == "asr":
        import numpy as np
        from faster_whisper import WhisperModel

        model = WhisperModel(
            str(root / "asr"),
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            local_files_only=True,
        )
        with wave.open(io.BytesIO(data), "rb") as audio:
            samples = (
                np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32)
                / 32768
            )
        segments, _ = model.transcribe(
            samples,
            language="zh",
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = "".join(
            segment.text
            for segment in segments
            if segment.no_speech_prob < 0.8 and segment.avg_logprob > -1.5
        ).strip()
        sys.stdout.buffer.write(json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"))
    else:
        raise ValueError("Unknown speech operation")


if __name__ == "__main__":
    main()
