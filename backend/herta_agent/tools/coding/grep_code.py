"""Literal code search adapted from coding-agent@e121d82, using shared read boundaries."""

import asyncio
import json
import threading

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.coding.read_file import FILE_BYTES, decode_utf8, read_bounded_bytes
from herta_agent.tools.registry import ToolParameters, ToolSpec


class GrepParameters(ToolParameters):
    query: str = Field(min_length=1, max_length=300)
    path: str = Field(default=".", min_length=1, max_length=1000)
    limit: int = Field(default=30, ge=1, le=100)


def _search(repo: Repository, parameters: GrepParameters, stop: threading.Event) -> dict:
    start = repo.path(parameters.path)
    matches, scanned, total, skipped, result_bytes = [], 0, 0, 0, 0
    truncated = False
    for path in repo.files(start):
        if stop.is_set():
            break
        if scanned >= 2000 or total >= 16 * 1024 * 1024:
            truncated = True
            break
        scanned += 1
        remaining = 16 * 1024 * 1024 - total
        try:
            data = read_bounded_bytes(path, max_bytes=min(FILE_BYTES + 1, remaining + 1))
            if len(data) > remaining:
                truncated = True
                break
            total += len(data)
            text = decode_utf8(data)
        except ToolExecutionError:
            skipped += 1
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if stop.is_set():
                break
            if parameters.query not in line:
                continue
            entry = {"path": repo.relative(path), "line": number, "text": line[:1000]}
            if len(line) > 1000:
                entry["line_truncated"] = True
            size = len(json.dumps(entry, ensure_ascii=False).encode("utf-8")) + 2
            if len(matches) == parameters.limit or result_bytes + size > 8000:
                truncated = True
                break
            matches.append(entry)
            result_bytes += size
        if truncated:
            break
    return {
        "matches": matches,
        "truncated": truncated,
        "skipped_files": skipped,
        "scanned_files": scanned,
    }


def grep_code(repo: Repository) -> ToolSpec:
    async def search(parameters: GrepParameters):
        stop = threading.Event()
        try:
            return await asyncio.to_thread(_search, repo, parameters, stop)
        finally:
            # Stop between files/lines; an OS read already in progress can still finish.
            stop.set()

    return ToolSpec(
        "grep_code",
        "在项目内按区分大小写的字面关键词搜索普通UTF-8文件，返回路径、行号和预览；"
        "truncated表示搜索不完整，skipped_files表示有文件无法搜索；不是正则或语义检索。",
        GrepParameters,
        search,
        permission="read_only",
    )
