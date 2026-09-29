"""Persistent source copy. Source checkout is never a write target."""

import asyncio
import json
import shutil
from pathlib import Path

from herta_agent.runtime.errors import AgentError
from herta_agent.tools.coding.paths import Repository


class Workspace(Repository):
    def __init__(self, source: Path, root: Path):
        super().__init__(root)
        self.source = source
        self.lock = asyncio.Lock()

    @classmethod
    def open(cls, source: Path):
        repo = Repository(source)
        root = repo.root / ".coding-agent-workspace"
        if root.is_symlink() or root.is_junction():
            raise AgentError("隔离副本路径不能是链接。")
        marker = root / ".coding-owner.json"
        if root.exists():
            try:
                if marker.is_symlink() or json.loads(marker.read_text(encoding="utf-8")) != {
                    "source": str(repo.root),
                    "version": 1,
                }:
                    raise ValueError()
            except (OSError, ValueError):
                raise AgentError("隔离副本缺少有效所有权记录；不会覆盖已有目录。") from None
            return cls(repo.root, root)
        root.mkdir()
        try:
            total = 0
            for number, path in enumerate(repo.files(repo.root), 1):
                total += path.stat().st_size
                if number > 10000 or total > 100 * 1024 * 1024:
                    raise AgentError("仓库副本超过 10000 文件/100MB 限制，请选择更小的源码目录。")
                target = root / path.relative_to(repo.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            marker.write_text(
                json.dumps({"source": str(repo.root), "version": 1}), encoding="utf-8"
            )
        except BaseException:
            # Only the exact new directory created above is removed on failed preparation.
            shutil.rmtree(root)
            raise
        return cls(repo.root, root)
