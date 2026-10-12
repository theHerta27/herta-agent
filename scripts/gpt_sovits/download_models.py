"""Download the minimal published GPT-SoVITS inference models, pinned by revision."""
import os
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(os.environ["HERTA_VOICE_RUNTIME"]).resolve()
REPO = "lj1995/GPT-SoVITS"
REVISION = "8f8857563c040d542de108a2c18b0425abd6c9c5"
FILES = [
    "chinese-hubert-base/config.json", "chinese-hubert-base/preprocessor_config.json",
    "chinese-hubert-base/pytorch_model.bin", "chinese-roberta-wwm-ext-large/config.json",
    "chinese-roberta-wwm-ext-large/pytorch_model.bin", "chinese-roberta-wwm-ext-large/tokenizer.json",
    "sv/pretrained_eres2netv2w24s4ep4.ckpt",
]

def download(name, meta):
    target = ROOT / "upstream/GPT_SoVITS/pretrained_models" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = meta.get("lfs", {}).get("sha256")
    if target.exists() and (not expected or hashlib.sha256(target.read_bytes()).hexdigest() == expected):
        return {"file": name, "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "cached": True}
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}?download=true"
    start = time.perf_counter()
    temporary = target.with_suffix(target.suffix + ".partial")
    for attempt in range(3):
        try:
            subprocess.run(["curl.exe", "--fail", "--location", "--silent", "--show-error", "--retry", "2", "--retry-all-errors", "--connect-timeout", "30", "--max-time", "600", "--output", str(temporary), url], check=True)
            sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if expected and sha != expected:
                raise ValueError(f"Published checksum mismatch: {name}")
            if temporary.stat().st_size != meta["size"]:
                raise ValueError(f"Published size mismatch: {name}")
            temporary.replace(target)
            result = {"file": name, "bytes": target.stat().st_size, "sha256": sha, "seconds": round(time.perf_counter() - start, 3)}
            print(json.dumps(result), flush=True)
            return result
        except Exception as exc:
            print(f"Download {name} attempt {attempt + 1}: {type(exc).__name__}: {exc}", flush=True)
            if attempt == 2:
                raise

if __name__ == "__main__":
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true", timeout=90) as response:
        info = json.load(response)
    assert info["sha"] == REVISION
    metadata = {item["rfilename"]: item for item in info["siblings"]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda name: download(name, metadata[name]), FILES))
    (ROOT / "base-model-manifest.json").write_text(json.dumps({"repository": REPO, "revision": REVISION, "files": results}, indent=2), encoding="utf-8")
