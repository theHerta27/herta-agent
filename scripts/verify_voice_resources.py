"""Recheck user-supplied voice assets without deserializing model weights."""

import hashlib
import json
import wave
from pathlib import Path


def verify(root):
    scope = root / "models/voice"
    manifest = json.loads(
        (scope / "the-herta/v2proplus/manifest.json").read_text("utf-8")
    )
    for item in manifest["files"]:
        path = (root / item["destination"]).resolve(strict=True)
        if not path.is_relative_to(scope.resolve()):
            raise ValueError("Resource path is outside the voice directory")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != item["bytes"] or digest != item["sha256"]:
            raise ValueError(f"Resource integrity mismatch: {path.name}")
        if path.suffix == ".wav":
            with wave.open(str(path), "rb") as audio:
                if (
                    audio.getnchannels(),
                    audio.getframerate(),
                    audio.getsampwidth(),
                ) != (item["channels"], item["sample_rate"], item["sample_width"]):
                    raise ValueError(f"Audio format mismatch: {path.name}")
    archive = root / manifest["archive"]["path"]
    with archive.open("rb") as stream:
        if (
            hashlib.file_digest(stream, "sha256").hexdigest()
            != manifest["archive"]["sha256"]
        ):
            raise ValueError("Original archive integrity mismatch")
    return len(manifest["files"])


if __name__ == "__main__":
    count = verify(Path(__file__).resolve().parents[1])
    print(
        f"Verified {count} voice resources and original archive; model bytes unchanged."
    )
