import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .service import validate_image


def recognize(data):
    validate_image(data)
    if os.name != "nt":
        raise ValueError("本地截图OCR目前支持Windows。")
    script = Path(__file__).resolve().parents[3] / "scripts/Local-OCR.ps1"
    with tempfile.TemporaryDirectory(prefix="Herta OCR ") as folder:
        target = Path(folder) / "capture.png"
        target.write_bytes(data)
        result = subprocess.run(
            [
                str(
                    Path(os.environ.get("SystemRoot", "C:/Windows"))
                    / "System32/WindowsPowerShell/v1.0/powershell.exe"
                ),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-ImagePath",
                str(target),
            ],
            capture_output=True,
            timeout=30,
            creationflags=0x08000000,
        )
        if result.returncode or len(result.stdout) > 100000:
            raise ValueError("Windows OCR不可用，请在系统中安装中文识别语言后重试。")
        value = json.loads(result.stdout.decode("utf-8-sig"))
        text = re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])", "", value["text"])
        return {
            "text": text[:10000],
            "truncated": len(text) > 10000,
            "language": value["language"],
            "engine": "Windows.Media.Ocr",
        }
