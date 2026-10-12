import hashlib
import os
import shutil
import stat
import time
from collections import defaultdict
from pathlib import Path

from .directory_guard import directory_guard
from .paths import INTERNAL, identity, linked, private


def scan(service, root_id, duplicates, stop, *, max_entries=20000):
    root = service.root(root_id)
    disk = shutil.disk_usage(root)
    started = time.monotonic()
    count, skipped, total, partial = 0, 0, 0, False
    stack = [(root, 0)]
    files, sizes, hints, buckets = [], defaultdict(int), {}, defaultdict(list)

    def checkpoint():
        if stop.is_set():
            return False
        service.root(root_id)
        return time.monotonic() - started < 30

    while stack and checkpoint():
        folder, depth = stack.pop()
        relative = folder.relative_to(root).as_posix() if folder != root else ""
        try:
            with directory_guard(folder), os.scandir(service.resolve(root_id, relative)) as entries:
                for item in entries:
                    if count >= max_entries or not checkpoint():
                        partial = True
                        stack.clear()
                        break
                    count += 1
                    path = Path(item.path)
                    try:
                        info = path.lstat()
                        if linked(info) or private(path.name):
                            skipped += 1
                            continue
                        entry = service.entry(root, path)
                        if stat.S_ISDIR(info.st_mode):
                            hints[entry["path"]] = entry["hint"]
                            if depth < 15:
                                stack.append((path, depth + 1))
                            else:
                                skipped += 1
                                partial = True
                        elif stat.S_ISREG(info.st_mode):
                            total += info.st_size
                            files.append(entry)
                            for parent in path.parents:
                                if parent == root:
                                    break
                                sizes[parent.relative_to(root).as_posix()] += info.st_size
                            # Dependency caches are measured from metadata, never hashed.
                            if (
                                duplicates
                                and 0 < info.st_size <= 64 * 1024 * 1024
                                and info.st_nlink == 1
                                and not any(
                                    p.lower() in INTERNAL or private(p)
                                    for p in path.relative_to(root).parts
                                )
                            ):
                                buckets[info.st_size].append((path, info))
                        else:
                            skipped += 1
                    except (OSError, ValueError):
                        skipped += 1
        except (OSError, ValueError):
            skipped += 1
    if stack or stop.is_set():
        partial = True
    groups, hashed_bytes, candidates = [], 0, 0
    hash_limited = False
    if duplicates and not stop.is_set():
        for size, members in buckets.items():
            if len(members) < 2:
                continue
            by_hash = defaultdict(list)
            for path, before in members:
                if (
                    not checkpoint()
                    or candidates >= 2000
                    or hashed_bytes + size > 512 * 1024 * 1024
                ):
                    hash_limited = True
                    break
                candidates += 1
                digest = hashlib.sha256()
                try:
                    relative = path.relative_to(root).as_posix()
                    service.resolve(root_id, relative, text=True)
                    with directory_guard(path.parent), path.open("rb") as stream:
                        if identity(os.fstat(stream.fileno())) != identity(before):
                            skipped += 1
                            continue
                        service.resolve(root_id, relative, text=True)
                        read = 0
                        while checkpoint():
                            chunk = stream.read(min(1024 * 1024, size - read + 1))
                            if not chunk:
                                break
                            digest.update(chunk)
                            read += len(chunk)
                            hashed_bytes += len(chunk)
                            if read > size:
                                break
                        after = os.fstat(stream.fileno())
                    if read != size or (before.st_size, before.st_mtime_ns) != (
                        after.st_size,
                        after.st_mtime_ns,
                    ):
                        skipped += 1
                        continue
                    by_hash[digest.hexdigest()].append(relative)
                except (OSError, ValueError):
                    skipped += 1
            for paths in by_hash.values():
                if len(paths) > 1:
                    groups.append({"size": size, "count": len(paths), "paths": sorted(paths)[:5]})
            if hash_limited:
                break
    files.sort(key=lambda f: (-f["size"], f["path"]))
    directories = [{"path": p, "size": s, "hint": hints.get(p, "folder")} for p, s in sizes.items()]
    directories.sort(key=lambda d: (-d["size"], d["path"]))
    groups.sort(key=lambda g: -g["size"] * (g["count"] - 1))
    return {
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "logical_bytes": total,
        "entries": count,
        "skipped": skipped,
        "partial": partial or skipped > 0 or hash_limited,
        "files": files[:40],
        "directories": directories[:20],
        "duplicates": groups[:20],
        "duplicates_checked": bool(duplicates),
        "hash_limited": hash_limited,
        "limits": (
            "最多 20,000 项、16 层、30 秒；重复候选 ≤64 MiB/文件、总读取 ≤512 MiB、2,000 项。"
            "跳过敏感文件和链接；硬链接不参与重复检查；缓存仅统计大小。"
        ),
        "suggestions": [
            "按文档、图片和安装包分类可便于查找；工程目录建议整体保留。",
            "重复内容仅为候选，需检查用途；缓存大小不代表可以安全删除。",
        ],
    }
