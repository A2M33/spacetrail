"""Compare two snapshots and point at the folders that actually changed."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .store import Snapshot

# A folder is only worth listing if its listed subfolders don't already explain most of
# its change. Otherwise we'd print C:\Users, C:\Users\you and C:\Users\you\Downloads
# for a single download.
EXPLAINED_BY_CHILDREN = 0.8


@dataclass(frozen=True)
class Change:
    path: str
    delta: int
    before: int
    after: int


def pick_baseline(snaps: list[Snapshot], days: float) -> tuple[Snapshot, Snapshot] | None:
    """Latest snapshot, and the newest one at least `days` older (or the oldest we have)."""
    if len(snaps) < 2:
        return None
    latest = snaps[-1]
    cutoff = latest.taken - days * 86400
    older = [s for s in snaps[:-1] if s.taken <= cutoff]
    return (older[-1] if older else snaps[0]), latest


def changes(before: dict[str, int], after: dict[str, int]) -> dict[str, Change]:
    out = {}
    for path in before.keys() | after.keys():
        b, a = before.get(path, 0), after.get(path, 0)
        if a != b:
            out[path] = Change(path, a - b, b, a)
    return out


def culprits(all_changes: dict[str, Change], min_bytes: int, limit: int, growing: bool = True) -> list[Change]:
    """The most specific folders behind the biggest changes in one direction."""
    sign = 1 if growing else -1
    big = {p: c for p, c in all_changes.items() if c.delta * sign >= min_bytes}

    children: dict[str, list[Change]] = {}
    for c in big.values():
        parent = os.path.dirname(c.path)
        if parent != c.path:  # dirname("C:\\") is "C:\\" again
            children.setdefault(parent, []).append(c)

    picked = []
    for c in big.values():
        kids = children.get(c.path, [])
        if sum(k.delta * sign for k in kids) >= EXPLAINED_BY_CHILDREN * c.delta * sign:
            continue
        picked.append(c)
    picked.sort(key=lambda c: c.delta * sign, reverse=True)
    return picked[:limit]


def human(n: int, signed: bool = False) -> str:
    sign = ("+" if n > 0 else "-" if n < 0 else "") if signed else ("-" if n < 0 else "")
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{sign}{n:.0f} {unit}" if unit == "B" else f"{sign}{n:.1f} {unit}"
        n /= 1024
    raise AssertionError  # unreachable


def parse_size(text: str) -> int:
    """'500MB' -> bytes. Plain numbers are megabytes."""
    t = text.strip().upper().replace(" ", "")
    units = {"TB": 1024**4, "GB": 1024**3, "MB": 1024**2, "KB": 1024, "B": 1}
    for unit, mult in units.items():
        if t.endswith(unit):
            return int(float(t[: -len(unit)]) * mult)
    return int(float(t) * 1024**2)


def parse_days(text: str) -> float:
    """'7d', '2w', '12h', or a plain number of days."""
    t = text.strip().lower()
    mult = {"h": 1 / 24, "d": 1, "w": 7, "m": 30}
    if t and t[-1] in mult:
        return float(t[:-1]) * mult[t[-1]]
    return float(t)
