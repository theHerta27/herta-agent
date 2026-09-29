"""Strict unified text diffs: validate every hunk before any file write."""

import difflib
import os
import re
import tempfile

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.registry import ToolParameters, ToolSpec


class PatchParameters(ToolParameters):
    patch: str = Field(min_length=1, max_length=128000)


def invalid(message="补丁无法干净应用；没有修改文件。"):
    return ToolExecutionError("patch_conflict", message)


def checked_changes(workspace, patch):
    lines = patch.splitlines(keepends=True)
    changes, index = [], 0
    while index < len(lines):
        if lines[index].startswith(("diff --git ", "index ")):
            index += 1
            continue
        if (
            not lines[index].startswith("--- ")
            or index + 1 >= len(lines)
            or not lines[index + 1].startswith("+++ ")
        ):
            raise invalid()
        old, new = [line[4:].rstrip("\r\n") for line in lines[index : index + 2]]
        if (
            old != "/dev/null"
            and not old.startswith("a/")
            or new != "/dev/null"
            and not new.startswith("b/")
        ):
            raise invalid()
        if (
            old == new == "/dev/null"
            or old != "/dev/null"
            and new != "/dev/null"
            and old[2:] != new[2:]
        ):
            raise invalid("不支持重命名；请使用明确的新增/删除文本补丁。")
        relative = new[2:] if new != "/dev/null" else old[2:]
        path = workspace.path(relative, exists=old != "/dev/null")
        lexical = workspace.root / relative
        for parent in (lexical, *lexical.parents):
            if parent == workspace.root:
                break
            if parent.is_symlink() or parent.is_junction():
                raise invalid("写入路径不能包含链接。")
        if path == workspace.root or any(p == path for p, _, _ in changes) or len(changes) >= 20:
            raise invalid()
        if old == "/dev/null" and path.exists():
            raise invalid()
        before = None
        if path.exists():
            if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 1024 * 1024:
                raise invalid()
            before = path.read_bytes()
        try:
            source = (before or b"").decode("utf-8").splitlines(keepends=True)
        except UnicodeError:
            raise invalid("仅支持 UTF-8 文本补丁。") from None
        if b"\x00" in (before or b""):
            raise invalid()
        newline = "\r\n" if before and b"\r\n" in before else "\n"
        output, cursor, hunks = [], 0, 0
        index += 2
        while index < len(lines) and lines[index].startswith("@@ "):
            header = re.fullmatch(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?", lines[index]
            )
            if not header:
                raise invalid()
            start, count, newstart, newcount = (
                int(header[1]),
                int(header[2] or 1),
                int(header[3]),
                int(header[4] or 1),
            )
            offset = start - 1 if count else start
            if offset < cursor or offset > len(source):
                raise invalid()
            output.extend(source[cursor:offset])
            if (newstart - 1 if newcount else newstart) != len(output):
                raise invalid()
            removed, added = [], []
            index += 1
            while index < len(lines) and (len(removed) < count or len(added) < newcount):
                line = lines[index]
                if not line or line[0] not in " +-":
                    raise invalid()
                content = line[1:].rstrip("\r\n") + newline
                index += 1
                if index < len(lines) and lines[index].startswith("\\ No newline at end of file"):
                    content = content.rstrip("\r\n")
                    index += 1
                if line[0] in " -":
                    removed.append(content)
                if line[0] in " +":
                    added.append(content)
            if (
                len(removed) != count
                or len(added) != newcount
                or source[offset : offset + count] != removed
            ):
                raise invalid()
            output.extend(added)
            cursor = offset + count
            hunks += 1
        if not hunks:
            raise invalid()
        output.extend(source[cursor:])
        if new == "/dev/null" and output:
            raise invalid()
        after = None if new == "/dev/null" else "".join(output).encode("utf-8")
        changes.append((path, before, after))
    if not changes:
        raise invalid("补丁没有任何文件修改。")
    return changes


def apply_patch(workspace):
    async def apply(p):
        async with workspace.lock:
            changes = checked_changes(workspace, p.patch)
            written = []
            try:
                for path, before, after in changes:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if after is None:
                        path.unlink()
                    else:
                        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".coding-patch-")
                        try:
                            with os.fdopen(fd, "wb") as stream:
                                stream.write(after)
                            os.replace(temporary, path)
                        finally:
                            if os.path.exists(temporary):  # noqa: ASYNC240 - bounded synchronous commit
                                os.unlink(temporary)
                    written.append((path, before))
            except OSError:
                for path, before in reversed(written):
                    if before is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(before)
                raise ToolExecutionError(
                    "patch_write_failed", "写入失败，已回滚本次文件修改。"
                ) from None
            return {
                "applied": True,
                "files": [
                    {
                        "path": workspace.relative(path),
                        "before_bytes": len(before or b""),
                        "after_bytes": len(after or b""),
                        "diff": "".join(
                            difflib.unified_diff(
                                (before or b"").decode("utf-8").splitlines(keepends=True),
                                (after or b"").decode("utf-8").splitlines(keepends=True),
                                fromfile="a/" + workspace.relative(path),
                                tofile="b/" + workspace.relative(path),
                            )
                        )[:8000],
                    }
                    for path, before, after in changes
                ],
            }

    return ToolSpec(
        "apply_patch",
        "仅向隔离副本应用 unified diff；所有文件/行先检查，无模糊匹配。"
        "仅 UTF-8 新增、修改、删除，不支持 rename/binary。",
        PatchParameters,
        apply,
    )
