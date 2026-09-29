"""Filesystem boundary for trusted coding repositories; not an OS sandbox."""

import os
from pathlib import Path

from herta_agent.runtime.errors import AgentError, ToolExecutionError

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".local",
    ".coding-agent-workspace",
    ".env",
    ".idea",
    ".ruff_cache",
    "dist",
}


def excluded(name: str) -> bool:
    return name.lower() in EXCLUDED or name.lower().startswith((".env.", ".coding-"))


class Repository:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise AgentError("请设置有效的 HERTA_CODING_REPO_ROOT 目录。")

    def path(self, raw: str, *, exists: bool = True) -> Path:
        candidate = Path(raw)
        parts = candidate.parts[1:] if candidate.anchor else candidate.parts
        if not raw or any(
            excluded(p)
            or ":" in p
            or p.rstrip(" .") != p
            and p not in (".", "..")
            or p.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"COM{i}" for i in range(10)],
                *[f"LPT{i}" for i in range(10)],
            }
            for p in parts
        ):
            raise ToolExecutionError("path_denied", "路径不在允许的源码范围内。")
        target = (self.root / candidate).resolve()
        if not target.is_relative_to(self.root):
            raise ToolExecutionError("path_denied", "路径不在允许的源码范围内。")
        if any(excluded(p) for p in target.relative_to(self.root).parts):
            raise ToolExecutionError("path_denied", "不允许访问内部或排除目录。")
        if exists and not target.exists():
            raise ToolExecutionError("path_missing", "路径不存在。")
        return target

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def files(self, start: Path):
        if start.is_file():
            yield start
            return
        for folder, dirs, files in os.walk(start, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if not excluded(d)
                and not (Path(folder) / d).is_symlink()
                and not (Path(folder) / d).is_junction()
            )
            for name in sorted(files):
                path = Path(folder) / name
                if not excluded(name) and not path.is_symlink():
                    yield self.path(str(path))
