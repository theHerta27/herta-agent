"""Read-path subset adapted from coding-agent@e121d82; not an OS sandbox."""

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
WINDOWS_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *[f"COM{i}" for i in range(10)],
    *[f"LPT{i}" for i in range(10)],
}


def excluded(name: str) -> bool:
    return name.lower() in EXCLUDED or name.lower().startswith((".env.", ".coding-"))


class Repository:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise AgentError("--repo 必须指定存在的项目目录。")

    def path(self, raw: str) -> Path:
        candidate = Path(raw)
        parts = candidate.parts[1:] if candidate.anchor else candidate.parts
        if not raw or any(
            excluded(part)
            or ":" in part
            or (part.rstrip(" .") != part and part not in (".", ".."))
            or part.split(".")[0].upper() in WINDOWS_DEVICES
            for part in parts
        ):
            raise ToolExecutionError("path_denied", "路径不在允许的源码范围内。")
        target = (self.root / candidate).resolve()
        if not target.is_relative_to(self.root):
            raise ToolExecutionError("path_denied", "路径不在允许的源码范围内。")
        if any(excluded(part) for part in target.relative_to(self.root).parts):
            raise ToolExecutionError("path_denied", "不允许访问内部或排除目录。")
        if not target.exists():
            raise ToolExecutionError("path_missing", "路径不存在。")
        return target

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def files(self, start: Path):
        """Read-only walk adapted from coding-agent@e121d82; skip links/internal paths."""
        if start.is_file():
            yield start
            return
        if not start.is_dir():
            raise ToolExecutionError("not_searchable", "请指定普通文件或目录。")

        def unreadable(error):
            raise ToolExecutionError(
                "directory_unreadable", "目录无法遍历，请缩小搜索范围。"
            ) from None

        for count, (folder, directories, names) in enumerate(
            os.walk(start, followlinks=False, onerror=unreadable), 1
        ):
            if count > 2000:
                raise ToolExecutionError("directory_limit", "目录数量超过限制，请缩小搜索范围。")
            directories[:] = sorted(
                name
                for name in directories
                if not excluded(name)
                and not (Path(folder) / name).is_symlink()
                and not (Path(folder) / name).is_junction()
            )
            for name in sorted(names):
                path = Path(folder) / name
                if not excluded(name) and not path.is_symlink() and path.is_file():
                    yield self.path(self.relative(path))
