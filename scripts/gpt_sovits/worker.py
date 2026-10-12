"""Owned local GPT-SoVITS process: JSON lines on stdin/stdout, binary WAV output.

Protocol: request {id,text,emotion,output_path}; reply {id,ok,wav_path,sample_rate,
duration_seconds,synthesis_seconds}. All upstream diagnostics go to stderr.
{"id": ..., "command": "shutdown"} exits cleanly. No external network is used.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import wave
import socket

SCRIPTS = Path(__file__).resolve().parent
PROJECT = SCRIPTS.parent.parent
ROOT = Path(os.environ.get("HERTA_VOICE_RUNTIME", str(PROJECT / ".local/gpt-sovits"))).resolve()

ROLE = PROJECT / "models/voice/the-herta/v2proplus"
UPSTREAM = ROOT / "upstream"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["G2PW"] = "0"
os.environ["PYTHONUTF8"] = "1"
os.environ["MPLBACKEND"] = "Agg"
os.environ["MPLCONFIGDIR"] = str(ROOT / "cache/matplotlib")
os.environ["HF_HUB_CACHE"] = str(ROOT / "cache/huggingface")
os.environ["NUMBA_CACHE_DIR"] = str(ROOT / "cache/numba")
os.environ["CUDA_CACHE_PATH"] = str(ROOT / "cache/cuda")
os.environ["NLTK_DATA"] = str(ROOT / "cache/nltk_data")
os.chdir(UPSTREAM)
sys.path.insert(0, str(UPSTREAM))
sys.path.insert(0, str(UPSTREAM / "GPT_SoVITS"))
sys.path.insert(0, str(SCRIPTS))

# This owned stdin/stdout process has no network API. Block Python network access
# as well as Hugging Face online mode so inference cannot fetch missing assets.
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
def _offline_connect(connection, address):
    if connection.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError("GPT-SoVITS inference is offline; network connections are disabled")
    return _original_connect(connection, address)
def _offline_connect_ex(connection, address):
    if connection.family in (socket.AF_INET, socket.AF_INET6):
        raise RuntimeError("GPT-SoVITS inference is offline; network connections are disabled")
    return _original_connect_ex(connection, address)
def _offline_resolution(*args, **kwargs):
    raise RuntimeError("GPT-SoVITS inference is offline; DNS and network connections are disabled")
socket.socket.connect = _offline_connect
socket.socket.connect_ex = _offline_connect_ex
socket.create_connection = _offline_resolution
socket.getaddrinfo = _offline_resolution

def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)

def make_engine(device="cuda"):
    role_manifest = json.loads((ROLE / "manifest.json").read_text(encoding="utf-8"))
    base_manifest = json.loads((SCRIPTS / "base-model-manifest.json").read_text(encoding="utf-8"))
    for item in role_manifest["files"]:
        path = PROJECT / item["destination"]
        if not path.resolve().is_relative_to(ROLE.resolve()):
            raise ValueError("Role manifest scope mismatch")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != item["bytes"] or digest != item["sha256"]:
            raise ValueError("Role asset checksum mismatch")
    for item in base_manifest["files"]:
        path = UPSTREAM / "GPT_SoVITS/pretrained_models" / item["file"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != item["bytes"] or digest != item["sha256"]:
            raise ValueError("Base model checksum mismatch")
    with contextlib.redirect_stdout(sys.stderr):
        print("Initializing isolated local GPT-SoVITS libraries...", file=sys.stderr, flush=True)
        import strict_loading
        strict_loading.install()
        import torch
        from TTS_infer_pack.TTS import TTS, TTS_Config
        torch.set_num_threads(4)
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Configured CUDA device is unavailable")
        config = TTS_Config({"custom": {
            "device": device, "is_half": device == "cuda", "version": "v2ProPlus",
            "t2s_weights_path": str(ROLE / "gpt.ckpt"),
            "vits_weights_path": str(ROLE / "sovits.pth"),
            "bert_base_path": str(UPSTREAM / "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"),
            "cnhuhbert_base_path": str(UPSTREAM / "GPT_SoVITS/pretrained_models/chinese-hubert-base"),
        }})
        config.configs_path = str(ROOT / "runtime-effective.yaml")
        print("Loading pinned local Great Herta and pretrained weights...", file=sys.stderr, flush=True)
        return TTS(config)

def synthesize(engine, request):
    import numpy as np
    text = request["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("text must contain 1-1000 characters")
    emotion = request.get("emotion", "neutral")
    references = json.loads((ROLE / "manifest.json").read_text(encoding="utf-8"))["files"]
    reference = next((item for item in references if item["destination"].endswith(f"references/{emotion}.wav")), None)
    if reference is None:
        raise ValueError("emotion must be neutral, surprised, happy, angry or sad")
    output = Path(request["output_path"]).resolve()
    if not output.is_relative_to(ROOT) or output.suffix != ".wav" or output.exists():
        raise ValueError("Output must be a new owned runtime WAV")
    output.parent.mkdir(parents=True, exist_ok=True)
    parameters = {
        "text": text, "text_lang": "all_zh", "ref_audio_path": str(ROLE / "references" / f"{emotion}.wav"),
        "prompt_text": reference["reference_text"], "prompt_lang": "all_zh",
        "text_split_method": "cut5", "batch_size": 1, "bucket_threshold": 0.75,
        "top_k": 5, "top_p": 1.0, "temperature": 1.0, "speed_factor": 1.0,
        "fragment_interval": 0.3, "seed": 42, "parallel_infer": True,
        "split_bucket": True, "return_fragment": False, "streaming_mode": False,
        "repetition_penalty": 1.35, "super_sampling": False,
    }
    start = time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr):
        segments = list(engine.run(parameters))
    if not segments:
        raise RuntimeError("Synthesis produced no audio")
    sr = segments[0][0]
    audio = np.concatenate([item[1] for item in segments]).astype(np.int16)
    if not len(audio) or np.max(np.abs(audio.astype(np.int32))) <= 50:
        raise RuntimeError("Synthesis produced empty or silent audio")
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(audio.tobytes())
    return {
        "wav_path": str(output), "sample_rate": sr, "duration_seconds": len(audio) / sr,
        "synthesis_seconds": round(time.perf_counter() - start, 3), "peak": int(np.max(np.abs(audio.astype(np.int32)))),
        "rms": float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))),
        "wav_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--once", help="JSON request file; synthesize and exit")
    args = parser.parse_args()
    begin = time.perf_counter()
    engine = make_engine(args.device)
    initialization = round(time.perf_counter() - begin, 3)
    if args.once:
        request_path = Path(args.once)
        if not request_path.is_absolute():
            request_path = ROOT / request_path
        request = json.loads(request_path.read_text(encoding="utf-8"))
        import strict_loading
        emit({"id": request.get("id"), "ok": True, "initialization_seconds": initialization, **synthesize(engine, request), "checkpoint_loads": strict_loading.LOAD_AUDIT})
    else:
        emit({"type": "ready", "protocol": 1, "device": args.device, "initialization_seconds": initialization})
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                if request.get("command") == "shutdown":
                    emit({"id": request.get("id"), "ok": True, "shutdown": True})
                    break
                emit({"id": request.get("id"), "ok": True, **synthesize(engine, request)})
            except Exception as exc:
                emit({"id": request.get("id") if isinstance(request, dict) else None, "ok": False, "error": str(exc)})
