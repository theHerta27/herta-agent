"""Bounded UTF-8 reader adapted from coding-agent@e121d82."""

import asyncio
import hashlib
import json
from pathlib import Path

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.registry import ToolParameters, ToolSpec

FILE_BYTES = 1024 * 1024


def read_bounded_bytes(path: Path, *, max_bytes: int = FILE_BYTES + 1) -> bytes:
    """Shared bounded disk read for Read and Search; the caller handles the result."""
    try:
        with path.open("rb") as stream:
            return stream.read(max_bytes)
    except OSError:
        raise ToolExecutionError("file_unreadable", "文件无法读取。") from None


def decode_utf8(data: bytes) -> str:
    if len(data) > FILE_BYTES:
        raise ToolExecutionError("file_too_large", "仅支持不超过1 MiB的文本文件。")
    try:
        if b"\x00" in data:
            raise UnicodeError()
        return data.decode("utf-8")
    except UnicodeError:
        raise ToolExecutionError("not_text", "仅支持 UTF-8 文本。") from None


class ReadParameters(ToolParameters):
    path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


def _read_file(repo: Repository, parameters: ReadParameters) -> dict:
    path = repo.path(parameters.path)
    if not path.is_file():
        raise ToolExecutionError("not_file", "请指定文本文件。")
    if parameters.end_line is not None and parameters.end_line < parameters.start_line:
        raise ToolExecutionError("invalid_range", "结束行不能小于起始行。")
    data = read_bounded_bytes(path)
    text = decode_utf8(data)

    source = text.splitlines()
    end = min(parameters.end_line or len(source), len(source))
    lines, size = [], 0
    truncated = False
    for index in range(parameters.start_line - 1, end):
        entry = {"line": index + 1, "text": source[index]}
        entry_bytes = len(json.dumps(entry, ensure_ascii=False).encode("utf-8")) + 2
        # Leave room for both the 64 KB envelope and the default context's next request.
        if len(lines) >= 400 or size + entry_bytes > 24_000:
            if not lines:
                raise ToolExecutionError("line_too_long", "单行内容过长，无法作为工具结果返回。")
            truncated = True
            break
        lines.append(entry)
        size += entry_bytes
    return {
        "path": repo.relative(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "lines": lines,
        "truncated": truncated,
        "next_line": lines[-1]["line"] + 1 if lines and truncated else None,
    }


def read_file(repo: Repository) -> ToolSpec:
    async def read(parameters: ReadParameters):
        # Cancellation stops waiting; an already-started read finishes in Runner's executor.
        return await asyncio.to_thread(_read_file, repo, parameters)

    return ToolSpec(
        "read_file",
        "读取项目内 UTF-8 文本并返回真实行号；可指定起止行，truncated表示结果不完整。",
        ReadParameters,
        read,
        permission="read_only",
    )
