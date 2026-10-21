"""Create one new UTF-8 file after approval, without replacing an existing path."""

import asyncio
import difflib
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.coding.read_file import decode_utf8
from herta_agent.tools.registry import ToolParameters, ToolSpec


class CreateParameters(ToolParameters):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=32000)


@dataclass(frozen=True)
class PreparedCreate:
    path: Path
    data: bytes
    diff: str


def create_path(repo: Repository, raw: str) -> Path:
    try:
        candidate = Path(raw)
        if candidate.anchor or ".." in candidate.parts or not raw.isprintable():
            raise ValueError
        target = repo.path(raw, allow_missing=True)
        lexical = repo.root / raw
        for part in (lexical, *lexical.parents):
            if part == repo.root:
                break
            if part.is_symlink() or part.is_junction():
                raise ValueError
    except (OSError, ValueError, RuntimeError):
        raise ToolExecutionError(
            "path_denied", "新建路径须在项目内，不能包含链接或特殊路径。"
        ) from None
    if target.exists():
        raise ToolExecutionError("create_conflict", "目标已存在，未覆盖；请先读取或换用新文件名。")
    if not target.parent.is_dir():
        raise ToolExecutionError("parent_missing", "父目录不存在；本工具不自动创建目录。")
    return target


def prepare_create(repo: Repository, parameters: CreateParameters) -> PreparedCreate:
    path = create_path(repo, parameters.path)
    try:
        data = parameters.content.encode("utf-8")
    except UnicodeError:
        raise ToolExecutionError("not_text", "新文件内容必须是有效UTF-8文本。") from None
    decode_utf8(data)  # Share Read's text/NUL contract; preserve the actual bytes.
    relative = repo.relative(path)
    if not data:
        diff = "--- /dev/null\n+++ b/" + relative + "\n（新建空文件）\n"
    else:
        diff = "".join(
            line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            for line in difflib.unified_diff(
                [],
                parameters.content.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile="b/" + relative,
            )
        )
    if len(diff.encode("utf-8")) > 16000:
        raise ToolExecutionError("create_too_large", "新文件差异过大，无法完整预览；请缩小内容。")
    return PreparedCreate(path, data, diff)


def commit_create(repo: Repository, parameters: CreateParameters, change: PreparedCreate) -> dict:
    """Publish complete staged bytes with os.link's no-overwrite behavior; no await here."""
    temporary = None
    try:
        target = create_path(repo, parameters.path)
        if target != change.path:
            raise ToolExecutionError("create_conflict", "目标路径已变化，未应用此次新建。")
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".coding-create-")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(change.data)
        if create_path(repo, parameters.path) != target:
            raise ToolExecutionError("create_conflict", "目标路径已变化，未应用此次新建。")
        os.link(temporary, target)  # Same directory/volume; refuses an existing destination.
    except FileExistsError:
        raise ToolExecutionError(
            "create_conflict", "目标已存在，未覆盖；请重新核对文件。"
        ) from None
    except OSError:
        raise ToolExecutionError(
            "create_write_failed", "新建失败或文件系统不支持；请核对目标。"
        ) from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                raise ToolExecutionError(
                    "create_cleanup_failed",
                    "目标可能已创建，但临时文件清理失败；请回读目标并核查。",
                ) from None
    return {
        "written": True,
        "created": True,
        "path": repo.relative(target),
        "after_sha256": hashlib.sha256(change.data).hexdigest(),
    }


def create_file(repo: Repository) -> ToolSpec:
    async def create(parameters: CreateParameters):
        change = await asyncio.to_thread(prepare_create, repo, parameters)
        await asyncio.sleep(0)
        return commit_create(repo, parameters, change)

    return ToolSpec(
        "create_file",
        "经逐次确认，在已有目录创建一个新UTF-8文件；可为空，不自动建目录、不覆盖已有目标。"
        "新建后应使用read_file回读核对；失败时检查实际状态，不盲目重试。",
        CreateParameters,
        create,
        permission="side_effect",
    )
