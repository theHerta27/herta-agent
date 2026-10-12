import ntpath
import os
import re
import stat
from pathlib import Path


class WorkspaceError(ValueError):
    pass


PRIVATE = {
    ".ssh",
    ".aws",
    ".codex",
    ".agents",
    ".gnupg",
    ".azure",
    ".kube",
    ".docker",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "credentials",
    "secrets",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "system volume information",
    "$recycle.bin",
}
CACHES = {"node_modules", ".venv", "venv", "__pycache__", ".cache", ".pytest_cache"}
INTERNAL = CACHES | {".git", ".local"}
TEXT = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".css",
    ".html",
    ".log",
}


def private(name):
    name = name.lower()
    return (
        name in PRIVATE
        or name.startswith(("credentials.", "secrets."))
        or name == ".env"
        or name.startswith(".env.")
        or name.startswith("id_rsa")
        or name.startswith("id_ed25519")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def identity(info):
    return f"{info.st_dev}:{info.st_ino}"


def check_chain(path):
    for part in reversed((path, *path.parents)):
        if linked(part.lstat()):
            raise WorkspaceError("不读取符号链接或重解析点。")


def grant_path(value):
    # Reject namespaces before normalization or filesystem calls.
    if len(value) > 240 or value.startswith(("\\\\", "//")) or not Path(value).is_absolute():
        raise WorkspaceError("请选择本机普通目录。")
    path = Path(value)
    if any(private(p) for p in path.parts):
        raise WorkspaceError("此目录包含受保护的个人配置。")
    if os.name == "nt":
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise WorkspaceError("暂不支持网络驱动器。")
        system = Path(os.environ.get("SystemRoot", "C:/Windows"))
        if path == system or system in path.parents:
            raise WorkspaceError("不授权 Windows 系统目录。")
    try:
        check_chain(path)
        if not path.is_dir():
            raise WorkspaceError("所选目录不存在。")
        return path.resolve(strict=True)
    except OSError:
        raise WorkspaceError("无法访问所选目录。") from None


def relative_parts(value):
    if not isinstance(value, str) or len(value) > 240 or ntpath.isabs(value) or ":" in value:
        raise WorkspaceError("需要目录内的相对路径。")
    parts = value.replace("\\", "/").split("/") if value else []
    if len(parts) > 16 or any(
        not p
        or p in {".", ".."}
        or p[-1] in " ."
        or any(ord(c) < 32 or c in '<>"|?*' for c in p)
        or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p)
        for p in parts
    ):
        raise WorkspaceError("路径包含不支持的名称。")
    return parts


def hint(path, info):
    name = path.name.lower()
    if linked(info):
        return "link"
    if private(name):
        return "protected"
    if name in CACHES:
        return "cache"
    if name in INTERNAL:
        return "protected"
    if stat.S_ISDIR(info.st_mode):
        from .directory_guard import directory_guard

        with directory_guard(path):
            for marker in (
                ".git",
                "package.json",
                "pyproject.toml",
                "Cargo.toml",
                "ProjectSettings",
            ):
                try:
                    (path / marker).lstat()  # Never follow a marker's link target.
                    return "project"
                except FileNotFoundError:
                    continue
        return "folder"
    if path.suffix.lower() == ".lnk":
        return "shortcut"
    return "file"
