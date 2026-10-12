"""Owned stdio adapter for the isolated, offline Great Herta runtime."""

import asyncio
import io
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4


class HertaSpeech:
    def __init__(self, root, *, python=None, worker=None):
        self.root = Path(root)
        self.python = python or self.root / ".venv/Scripts/python.exe"
        self.worker = worker or Path(__file__).resolve().parents[3] / "scripts/gpt_sovits/worker.py"
        self._children = set()
        self._slot = asyncio.Semaphore(1)

    @property
    def active_children(self):
        return len(self._children)

    def ready(self):
        return (
            self.python.is_file()
            and self.worker.is_file()
            and (self.root / "base-model-manifest.json").is_file()
        )

    async def shutdown(self):
        for child in tuple(self._children):
            if child.returncode is None:
                child.kill()
            await child.wait()

    async def synthesize(self, text, emotion="neutral"):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000 or "\x00" in text:
            raise ValueError("大黑塔朗读每段需为1–1000字。")
        if emotion not in {"neutral", "happy", "sad", "angry", "surprised"}:
            raise ValueError("语音情绪无效。")
        async with self._slot:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="speech-", dir=self.root) as folder:
                output = Path(folder) / "speech.wav"
                env = {
                    key: value
                    for key, value in os.environ.items()
                    if key.upper()
                    in {
                        "PATH",
                        "SYSTEMROOT",
                        "WINDIR",
                        "TEMP",
                        "TMP",
                        "LOCALAPPDATA",
                        "APPDATA",
                    }
                }
                env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HERTA_VOICE_RUNTIME=str(self.root))
                child = await asyncio.create_subprocess_exec(
                    str(self.python),
                    "-X",
                    "utf8",
                    str(self.worker),
                    "--device",
                    "cuda",
                    cwd=self.root,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=65536,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self._children.add(child)

                async def drain():
                    while await child.stderr.read(8192):
                        pass  # Diagnostics may contain paths; never return them to the renderer.

                draining = asyncio.create_task(drain())
                try:
                    async with asyncio.timeout(180):
                        ready = json.loads(await child.stdout.readline())
                        if ready.get("type") != "ready" or ready.get("protocol") != 1:
                            raise ValueError("音色推理环境未就绪。")
                        request_id = uuid4().hex
                        child.stdin.write(
                            (
                                json.dumps(
                                    {
                                        "id": request_id,
                                        "text": text,
                                        "emotion": emotion,
                                        "output_path": str(output),
                                    }
                                )
                                + "\n"
                            ).encode()
                        )
                        await child.stdin.drain()
                        result = json.loads(await child.stdout.readline())
                        if (
                            result.get("id") != request_id
                            or not result.get("ok")
                            or result.get("wav_path") != str(output)
                        ):
                            raise ValueError("音色合成失败。")
                        if not output.is_file() or output.stat().st_size > 12_000_000:
                            raise ValueError("合成声音大小无效。")
                        data = output.read_bytes()
                        with wave.open(io.BytesIO(data), "rb") as audio:
                            if (
                                audio.getnchannels() != 1
                                or audio.getsampwidth() != 2
                                or (audio.getframerate() != 32000 or audio.getnframes() <= 0)
                            ):
                                raise ValueError("合成声音格式无效。")
                        child.stdin.write(b'{"id":"stop","command":"shutdown"}\n')
                        await child.stdin.drain()
                        await child.stdout.readline()
                        await child.wait()
                        if child.returncode:
                            raise ValueError("音色进程退出异常。")
                        return data
                except (OSError, TimeoutError, ValueError, EOFError) as error:
                    raise ValueError("本机大黑塔合成失败，请检查独立环境或切换Piper。") from error
                finally:
                    if child.returncode is None:
                        child.kill()
                    await child.wait()
                    await draining
                    self._children.discard(child)
