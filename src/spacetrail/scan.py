"""Walk a folder tree and add up how much space each folder uses."""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows marks junctions and symlinks as "reparse points". Following them would count
# the same files twice (or loop forever), so we skip them like Explorer's size dialog does.
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# Linux pseudo-filesystems that look like folders but aren't real disk usage.
_SKIP_UNIX = {"/proc", "/sys", "/dev", "/run"}


@dataclass
class ScanResult:
    root: str
    sizes: dict[str, int] = field(default_factory=dict)  # folder -> bytes, including subfolders
    files: int = 0
    skipped: int = 0  # folders we weren't allowed to read
    depth: int = 6  # folder levels below root that got their own entry


def _is_link(entry: os.DirEntry) -> bool:
    if entry.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            return bool(entry.stat(follow_symlinks=False).st_file_attributes & _REPARSE)
        except OSError:
            return True
    return False


def scan(root: str | Path, depth: int = 6, progress=None) -> ScanResult:
    """Total size of every folder up to `depth` levels below root.

    Deeper folders still count, they just get added to their ancestor at `depth`.
    That keeps the database small while still pointing you at the right place.
    """
    root = os.path.abspath(root)
    result = ScanResult(root=root, depth=depth)
    root_dev = os.stat(root).st_dev
    totals: dict[str, int] = {root: 0}
    # Iterative walk: deep trees would hit Python's recursion limit.
    stack: list[tuple[str, int, str]] = [(root, 0, root)]  # (path, level, folder it counts toward)
    while stack:
        path, level, owner = stack.pop()
        try:
            it = os.scandir(path)
        except OSError:
            result.skipped += 1
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _is_link(entry) or entry.path in _SKIP_UNIX:
                            continue
                        if sys.platform != "win32" and entry.stat(follow_symlinks=False).st_dev != root_dev:
                            continue  # another disk mounted inside this one
                        child_owner = entry.path if level + 1 <= depth else owner
                        if child_owner == entry.path:
                            totals[entry.path] = 0
                        stack.append((entry.path, level + 1, child_owner))
                    elif entry.is_file(follow_symlinks=False):
                        totals[owner] += entry.stat(follow_symlinks=False).st_size
                        result.files += 1
                        if progress and result.files % 5000 == 0:
                            progress(result.files)
                except OSError:
                    continue

    # Roll each folder's own bytes up into all of its ancestors.
    for path in sorted(totals, key=len, reverse=True):
        if path == root:
            continue
        parent = os.path.dirname(path)
        if parent in totals:
            totals[parent] += totals[path]
    result.sizes = totals
    return result
