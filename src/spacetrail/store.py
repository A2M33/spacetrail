"""Snapshots live in one SQLite file, so there is nothing to install or run."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .scan import ScanResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (
    id INTEGER PRIMARY KEY,
    root TEXT NOT NULL,
    taken REAL NOT NULL,          -- unix time
    files INTEGER NOT NULL,
    disk_free INTEGER,            -- free bytes on that drive at scan time
    disk_total INTEGER,
    depth INTEGER                 -- folder levels stored; NULL in databases from 0.2 and older
);
CREATE TABLE IF NOT EXISTS folder (
    snapshot INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    PRIMARY KEY (snapshot, path)
) WITHOUT ROWID;
"""


@dataclass(frozen=True)
class Snapshot:
    id: int
    root: str
    taken: float
    files: int
    disk_free: int | None
    disk_total: int | None
    depth: int | None = None


def path_key(path: str) -> str:
    """Compare paths the way the OS does: C:\\Users and c:\\users are one folder on Windows."""
    return os.path.normcase(os.path.normpath(path))


def is_within(path: str, folder: str) -> bool:
    """True for `folder` itself and anything below it."""
    p, f = path_key(path), path_key(folder)
    return p == f or p.startswith(f if f.endswith(os.sep) else f + os.sep)


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "spacetrail"


def default_db() -> Path:
    return Path(os.environ.get("SPACETRAIL_DB", data_dir() / "snapshots.db"))


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        path = Path(path) if path else default_db()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(snapshot)")}
        if "depth" not in cols:  # databases from 0.2 and older
            with self.db:
                self.db.execute("ALTER TABLE snapshot ADD COLUMN depth INTEGER")

    def close(self) -> None:
        self.db.close()

    def save(
        self,
        result: ScanResult,
        disk: tuple[int, int] | None = None,
        taken: float | None = None,
        min_size: int = 1024**2,
    ) -> Snapshot:
        """Folders under `min_size` aren't stored; a full drive has tens of thousands of tiny ones."""
        taken = time.time() if taken is None else taken
        free, total = disk if disk else (None, None)
        with self.db:
            cur = self.db.execute(
                "INSERT INTO snapshot (root, taken, files, disk_free, disk_total, depth) VALUES (?, ?, ?, ?, ?, ?)",
                (result.root, taken, result.files, free, total, result.depth),
            )
            sid = cur.lastrowid
            self.db.executemany(
                "INSERT INTO folder (snapshot, path, size) VALUES (?, ?, ?)",
                ((sid, p, s) for p, s in result.sizes.items() if s >= min_size or p == result.root),
            )
        return Snapshot(sid, result.root, taken, result.files, free, total, result.depth)

    def snapshots(self, root: str | None = None) -> list[Snapshot]:
        sql = "SELECT id, root, taken, files, disk_free, disk_total, depth FROM snapshot ORDER BY taken"
        snaps = [Snapshot(*row) for row in self.db.execute(sql)]
        if root:
            key = path_key(root)
            snaps = [s for s in snaps if path_key(s.root) == key]
        return snaps

    def roots(self) -> list[str]:
        """Snapshot roots, spelled as in their newest snapshot."""
        latest = {path_key(s.root): s.root for s in self.snapshots()}
        return sorted(latest.values(), key=path_key)

    def root_for(self, path: str) -> str | None:
        """The snapshot root that is `path` or contains it (the closest one wins)."""
        found = [r for r in self.roots() if is_within(path, r)]
        return max(found, key=len) if found else None

    def sizes(self, snapshot_id: int) -> dict[str, int]:
        return dict(self.db.execute("SELECT path, size FROM folder WHERE snapshot = ?", (snapshot_id,)))

    def prune(self, keep_days: float, now: float | None = None) -> int:
        """Delete old snapshots, but always keep the newest one per folder."""
        now = time.time() if now is None else now
        cutoff = now - keep_days * 86400
        with self.db:
            cur = self.db.execute(
                """DELETE FROM snapshot WHERE taken < ? AND id NOT IN
                   (SELECT id FROM snapshot s WHERE taken = (SELECT MAX(taken) FROM snapshot WHERE root = s.root))""",
                (cutoff,),
            )
        return cur.rowcount
