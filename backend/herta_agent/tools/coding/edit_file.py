"""One exact replacement in an existing text file; no patch parser or command execution."""

import asyncio
import difflib
import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.coding.read_file import decode_utf8, read_bounded_bytes
from herta_agent.tools.registry import ToolParameters, ToolSpec


class EditParameters(ToolParameters):
    path: str = Field(min_length=1, max_length=1000)
    old_text: str = Field(min_length=1, max_length=32000)
    new_text: str = Field(max_length=32000)
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class PreparedEdit:
    path: Path
    before: bytes
    after: bytes
    diff: str


def editable_path(repo: Repository, raw: str) -> Path:
    target = repo.path(raw)
    if ".." in Path(raw).parts:
        raise ToolExecutionError("path_denied", "编辑路径不能包含上级目录。")
    lexical = repo.root / raw
    for part in (lexical, *lexical.parents):
        if part == repo.root:
            break
        if part.is_symlink() or part.is_junction():
            raise ToolExecutionError("path_denied", "编辑路径不能包含链接或联接。")
    if not target.is_file():
        raise ToolExecutionError("path_denied", "仅允许编辑已有普通文件。")
    metadata = target.stat()
    if metadata.st_nlink != 1 or not metadata.st_mode & stat.S_IWUSR:
        raise ToolExecutionError("path_denied", "不允许编辑硬链接或只读文件。")
    return target


def prepare_edit(repo: Repository, parameters: EditParameters) -> PreparedEdit:
    path = editable_path(repo, parameters.path)
    before = read_bounded_bytes(path)
    source = decode_utf8(before)
    if hashlib.sha256(before).hexdigest() != parameters.expected_sha256:
        raise ToolExecutionError("edit_conflict", "文件已变化，请重新读取后提出修改。")
    offset = source.find(parameters.old_text)
    if offset < 0 or source.find(parameters.old_text, offset + 1) >= 0:
        raise ToolExecutionError("edit_conflict", "原文本必须在文件中唯一出现，请提供更多上下文。")
    if parameters.old_text == parameters.new_text:
        raise ToolExecutionError("edit_conflict", "新旧文本相同，没有修改。")
    after = (
        source[:offset] + parameters.new_text + source[offset + len(parameters.old_text) :]
    ).encode("utf-8")
    decode_utf8(after)  # Keep the same UTF-8, NUL and size contract as Read.
    relative = repo.relative(path)
    diff = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in difflib.unified_diff(
            source.splitlines(keepends=True),
            after.decode("utf-8").splitlines(keepends=True),
            fromfile="a/" + relative,
            tofile="b/" + relative,
        )
    )
    if len(diff.encode("utf-8")) > 16000:
        raise ToolExecutionError("edit_too_large", "差异过大，无法完整预览；请缩小修改。")
    return PreparedEdit(path, before, after, diff)


def commit_edit(repo: Repository, parameters: EditParameters, change: PreparedEdit) -> dict:
    """Bounded synchronous commit: no await after entering the write section."""
    temporary = None
    try:
        target = editable_path(repo, parameters.path)
        if target != change.path or read_bounded_bytes(target) != change.before:
            raise ToolExecutionError("edit_conflict", "文件已变化，没有应用此次修改。")
        mode = stat.S_IMODE(target.stat().st_mode)
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".coding-edit-")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(change.after)
        os.chmod(temporary, mode)
        # Detect an ordinary external edit made while preparing the temporary file.
        if (
            editable_path(repo, parameters.path) != target
            or read_bounded_bytes(target) != change.before
        ):
            raise ToolExecutionError("edit_conflict", "文件已变化，没有应用此次修改。")
        os.replace(temporary, target)
    except OSError:
        raise ToolExecutionError("edit_write_failed", "文件写入失败，请重新读取核对。") from None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "written": True,
        "path": repo.relative(target),
        "before_sha256": parameters.expected_sha256,
        "after_sha256": hashlib.sha256(change.after).hexdigest(),
    }


def edit_file(repo: Repository) -> ToolSpec:
    async def edit(parameters: EditParameters):
        change = await asyncio.to_thread(prepare_edit, repo, parameters)
        await asyncio.sleep(0)  # Cancellation before the synchronous write section is safe.
        return commit_edit(repo, parameters, change)

    return ToolSpec(
        "edit_file",
        "在已有UTF-8文件中替换一处唯一文本，必须提供Read返回的expected_sha256；"
        "新旧文本要不同，不能创建、删除或重命名文件；每次需用户确认完整差异。",
        EditParameters,
        edit,
        permission="side_effect",
    )
