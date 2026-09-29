import asyncio

from pydantic import Field

from herta_agent.tools.registry import ToolParameters, ToolSpec


class GrepParameters(ToolParameters):
    query: str = Field(min_length=1, max_length=300)
    path: str = Field(default=".", min_length=1, max_length=1000)
    limit: int = Field(default=30, ge=1, le=100)


def grep_code(repo):
    async def search(p):
        start = repo.path(p.path)
        matches, scanned, total, skipped = [], 0, 0, 0
        truncated = False
        for path in repo.files(start):
            await asyncio.sleep(0)
            scanned += 1
            if scanned > 2000 or total >= 16 * 1024 * 1024:
                truncated = True
                break
            try:
                with path.open("rb") as stream:
                    data = stream.read(1024 * 1024 + 1)
                total += len(data)
                if len(data) > 1024 * 1024 or b"\x00" in data:
                    skipped += 1
                    continue
                text = data.decode("utf-8")
            except (OSError, UnicodeError):
                skipped += 1
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if p.query in line:
                    if len(matches) == p.limit:
                        truncated = True
                        break
                    matches.append(
                        {"path": repo.relative(path), "line": number, "text": line[:1000]}
                    )
                    if len(line) > 1000:
                        matches[-1]["line_truncated"] = True
            if truncated:
                break
        return {"matches": matches, "truncated": truncated, "skipped_files": skipped}

    return ToolSpec(
        "grep_code",
        "按字面关键词检索真实源码，返回路径、行号；非语义或向量检索。",
        GrepParameters,
        search,
    )
