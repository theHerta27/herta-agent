"""Create a private, self-contained Windows directory from explicit product inputs."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

IGNORED = {".git", "__pycache__", ".cache", ".ruff_cache", "uv-cache", "outputs", "cache"}


def build_product(source, destination, *, python_runtime, include_voice=True, embedding=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    allowed = (source / "release").resolve()
    if not destination.is_relative_to(allowed) or destination == allowed or destination.exists():
        raise ValueError("发行目标必须是项目release内不存在的新目录。")
    runtime = Path(python_runtime).resolve()
    if not runtime.is_relative_to(source) or not (runtime / "python.exe").is_file():
        raise ValueError("需要项目内完整的可分发Python运行时。")
    mandatory = ["frontend/dist", "frontend/desktop", "frontend/package.json",
                 "frontend/node_modules/electron/dist", "backend/herta_agent",
                 "knowledge", "persona", "scripts", ".venv"]
    if any(not (source / path).exists() for path in mandatory):
        raise ValueError("产品构建或依赖缺失，请先构建前端并准备Python环境。")
    destination.mkdir(parents=True)
    files, size = 0, 0

    def copy_file(original, relative):
        nonlocal files, size
        target = destination / relative
        if not target.resolve().is_relative_to(destination):
            raise ValueError("发行输出越界。")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        files += 1
        size += target.stat().st_size

    def copy_tree(original, relative):
        original = Path(original)
        if not original.is_dir():
            return
        for folder, dirs, names in os.walk(original, followlinks=False):
            dirs[:] = [d for d in dirs if d not in IGNORED and not Path(folder, d).is_symlink()]
            for name in names:
                if name.endswith((".pyc", ".partial")) or name == ".env":
                    continue
                file = Path(folder) / name
                if file.is_symlink():
                    raise ValueError("发行输入出现文件链接，请核对资源。")
                copy_file(file, Path(relative) / file.relative_to(original))

    for relative in mandatory:
        original = source / relative
        if original.is_dir():
            copy_tree(original, relative)
        else:
            copy_file(original, relative)
    for relative in ("README.md", "LICENSE", "backend/pyproject.toml", "backend/uv.lock"):
        if (source / relative).is_file():
            copy_file(source / relative, relative)
    if (source / "docs/PORTABLE_README.md").is_file():
        copy_file(source / "docs/PORTABLE_README.md", "README.md")
    copy_tree(runtime, ".local/python/runtime")
    for relative in ("zh_CN-huayan-medium.onnx", "zh_CN-huayan-medium.onnx.json"):
        original = source / ".local/voice" / relative
        if original.is_file():
            copy_file(original, Path(".local/voice") / relative)
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        original = source / ".local/voice/asr" / name
        if original.is_file():
            copy_file(original, Path(".local/voice/asr") / name)
    copy_tree(source / ".local/libreoffice/unpacked", ".local/libreoffice/unpacked")
    if embedding:
        model = Path(embedding).resolve()
        for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt",
                     "special_tokens_map.json", "pytorch_model.bin", "model.safetensors",
                     "README.md", "LICENSE", "sentence_bert_config.json"):
            if (model / name).is_file():
                copy_file(model / name, Path(".local/embedding/bge-large-zh") / name)
    if include_voice:
        voice = source / ".local/gpt-sovits"
        for name in (".venv", "upstream"):
            copy_tree(voice / name, Path(".local/gpt-sovits") / name)
        for name in ("base-model-manifest.json",):
            if (voice / name).is_file():
                copy_file(voice / name, Path(".local/gpt-sovits") / name)
        copy_tree(source / "models/voice/the-herta/v2proplus", "models/voice/the-herta/v2proplus")
        (destination / ".local/gpt-sovits/source-revision.txt").parent.mkdir(parents=True, exist_ok=True)
        (destination / ".local/gpt-sovits/source-revision.txt").write_text(
            "1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a", encoding="utf-8")
    for relative in (".venv", ".local/gpt-sovits/.venv"):
        venv = destination / relative
        if venv.is_dir():
            (venv / "pyvenv.cfg").write_text(
                f"home = {destination / '.local/python/runtime'}\n"
                "include-system-site-packages = false\nversion_info = 3.12.13\n", encoding="utf-8")
    (destination / ".venv/Lib/site-packages/_editable_impl_herta_agent.pth").write_text(
        str(destination / "backend") + "\n", encoding="utf-8")
    launcher = (
        '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass '
        '-File "%~dp0scripts\\Launch-Portable.ps1"\r\n'
    )
    (destination / "启动Herta.cmd").write_text(launcher, encoding="ascii")
    (destination / "启动离线演示.cmd").write_text(launcher.replace('.ps1"', '.ps1" -Demo'), encoding="ascii")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                         stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "fixture"
    result = {"format": "herta-portable-1", "source_commit": commit, "files": files,
              "bytes": size, "includes_herta_voice": include_voice,
              "includes_local_embedding": bool(embedding), "user_state_included": False}
    (destination / "PRODUCT-MANIFEST.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    # A short integrity manifest covers executable entrypoints; model manifests validate weights.
    hashes = {}
    for file in (destination / "frontend/dist/electron").glob("*.cjs"):
        hashes[str(file.relative_to(destination))] = hashlib.sha256(file.read_bytes()).hexdigest()
    (destination / "ENTRYPOINT-HASHES.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--lite", action="store_true")
    args = parser.parse_args()
    from herta_agent.rag.embeddings import find_local_model

    root = Path(__file__).resolve().parent.parent
    report = build_product(root, args.destination, python_runtime=Path(sys.base_prefix),
                           include_voice=not args.lite, embedding=find_local_model())
    finalize_environments(args.destination)
    print(json.dumps(report))


def finalize_environments(destination):
    destination = Path(destination).resolve()
    if not (destination / "PRODUCT-MANIFEST.json").is_file():
        raise ValueError("只能调整本工具创建的发行环境。")
    env = {**os.environ, "UV_VENV_CLEAR": "false"}
    for relative in (".venv", ".local/gpt-sovits/.venv"):
        venv = destination / relative
        if venv.is_dir():
            subprocess.run([
                "uv", "venv", "--allow-existing", "--relocatable", "--no-config",
                "--no-project", "--no-python-downloads", "--python",
                str(destination / ".local/python/runtime/python.exe"), str(venv),
            ], check=True, env=env)


if __name__ == "__main__":
    main()
