from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.registry import ToolParameters, ToolSpec


class ReadParameters(ToolParameters):
    path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


def read_file(repo):
    async def read(p):
        path = repo.path(p.path)
        if not path.is_file():
            raise ToolExecutionError("not_file", "请指定文本文件。")
        if p.end_line is not None and p.end_line < p.start_line:
            raise ToolExecutionError("invalid_range", "结束行不能小于起始行。")
        try:
            with path.open("rb") as stream:
                data = stream.read(1024 * 1024 + 1)
            if b"\x00" in data:
                raise UnicodeError()
            oversized = len(data) > 1024 * 1024
            text = data[: 1024 * 1024].decode("utf-8", errors="ignore" if oversized else "strict")
        except UnicodeError:
            raise ToolExecutionError("not_text", "仅支持 UTF-8 文本。") from None
        except OSError:
            raise ToolExecutionError("file_unreadable", "文件无法读取。") from None
        lines, size = [], 0
        source = text.splitlines()
        end = min(p.end_line or len(source), len(source))
        truncated = oversized
        for index in range(p.start_line - 1, end):
            line = source[index]
            if len(lines) >= 400 or size + len(line) > 32000:
                truncated = True
                break
            lines.append({"line": index + 1, "text": line})
            size += len(line)
        return {
            "path": repo.relative(path),
            "lines": lines,
            "truncated": truncated,
            "next_line": lines[-1]["line"] + 1 if lines and truncated else None,
        }

    return ToolSpec(
        "read_file",
        "读取 UTF-8 源码并返回真实行号；truncated 表示需缩小行范围。",
        ReadParameters,
        read,
    )
