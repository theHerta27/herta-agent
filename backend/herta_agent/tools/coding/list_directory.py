from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import excluded
from herta_agent.tools.registry import ToolParameters, ToolSpec


class ListParameters(ToolParameters):
    path: str = Field(default=".", min_length=1, max_length=1000)


def list_directory(repo):
    async def listing(p):
        path = repo.path(p.path)
        if not path.is_dir():
            raise ToolExecutionError("not_directory", "请指定目录。")
        entries = []
        for entry in sorted(path.iterdir()):
            if excluded(entry.name) or entry.is_symlink() or entry.is_junction():
                continue
            entries.append(
                {"path": repo.relative(entry), "kind": "directory" if entry.is_dir() else "file"}
            )
            if len(entries) > 200:
                break
        return {"entries": entries[:200], "truncated": len(entries) > 200}

    return ToolSpec(
        "list_directory",
        "列出仓库目录，排除 Git、依赖、环境和工作副本目录。",
        ListParameters,
        listing,
    )
