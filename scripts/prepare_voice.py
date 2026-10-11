"""Explicit public model preparation. Runtime speech never downloads or uploads."""

import hashlib
import json
import os
from pathlib import Path

os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / ".local" / "voice"


def create_manifest(destination, asr, tts):
    manifest = {"asr": asr, "tts": tts, "files": {}}
    for path in destination.rglob("*"):
        if (
            path.is_file()
            and ".cache" not in path.parts
            and path.name != "manifest.json"
            and path.suffix in {".bin", ".onnx", ".json"}
        ):
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            manifest["files"][str(path.relative_to(destination))] = digest
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download

    DESTINATION.mkdir(parents=True, exist_ok=True)
    api = HfApi(token=False)
    asr_repo = "Systran/faster-whisper-base"
    tts_repo = "rhasspy/piper-voices"
    asr_revision = api.model_info(asr_repo).sha
    tts_revision = api.model_info(tts_repo).sha
    print("Preparing multilingual local ASR...", flush=True)
    snapshot_download(
        asr_repo,
        revision=asr_revision,
        token=False,
        local_dir=DESTINATION / "asr",
        allow_patterns=[
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
            "preprocessor_config.json",
            "README.md",
        ],
        max_workers=2,
    )
    print("Preparing local Chinese TTS...", flush=True)
    voice = "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
    for name in (voice, voice + ".json", "zh/zh_CN/huayan/medium/MODEL_CARD"):
        path = Path(
            hf_hub_download(
                tts_repo,
                name,
                revision=tts_revision,
                token=False,
                local_dir=DESTINATION / "piper",
            )
        )
        if name.endswith((".onnx", ".json")):
            target = DESTINATION / path.name
            target.write_bytes(path.read_bytes())
    create_manifest(
        DESTINATION,
        {"repository": asr_repo, "revision": asr_revision},
        {"repository": tts_repo, "revision": tts_revision},
    )
    print("Local voice models ready. No audio or chat content was sent.", flush=True)


if __name__ == "__main__":
    main()
