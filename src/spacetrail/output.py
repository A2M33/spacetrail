"""How text looks in a terminal: colours, bars, and fitting lines to the window."""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
import unicodedata


class Style:
    """The A2M33 palette in a terminal: cyan marks what grew, dim is for labels, red only for errors."""

    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def bold(self, t): return self._wrap("1", t)
    def dim(self, t): return self._wrap("2", t)
    def signal(self, t): return self._wrap("38;5;45", t)  # 256-colour cyan, close to the signal token #2fcbea


def _windows_ansi_is_on() -> bool:
    # Old Windows consoles need ANSI colours switched on explicitly.
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        return bool(k.GetConsoleMode(h, ctypes.byref(mode)) and k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


def make_style() -> Style:
    if os.environ.get("NO_COLOR"):  # https://no-color.org
        return Style(False)
    if os.environ.get("FORCE_COLOR"):
        return Style(True)
    if not sys.stdout.isatty() or os.environ.get("TERM") == "dumb":
        return Style(False)
    return Style(_windows_ansi_is_on() if sys.platform == "win32" else True)


def terminal_width() -> int | None:
    """Columns to fit into, or None for a pipe or file: scripts want whole lines."""
    return shutil.get_terminal_size((80, 24)).columns if sys.stdout.isatty() else None


def _can_print(text: str) -> bool:
    # Some consoles and redirected output can't encode everything.
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def bar(value: int, top: int, width: int = 10) -> str:
    n = max(1, round(width * value / top)) if top else 0
    return ("█" if _can_print("█") else "#") * n + " " * (width - n)


def _char_cells(ch: str) -> int:
    if unicodedata.combining(ch) or unicodedata.category(ch) == "Cf":
        return 0  # accents, and the zero-width non-joiner in Persian
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def cells(text: str) -> int:
    """How many terminal columns `text` takes up."""
    return sum(_char_cells(ch) for ch in text)


def fit_path(path: str, width: int) -> str:
    """Cut a path down to `width` columns from the left, because its end names the folder."""
    if cells(path) <= width:
        return path
    dots = "…" if _can_print("…") else "..."
    room = width - cells(dots)
    kept = len(path)
    while kept > 0 and room - _char_cells(path[kept - 1]) >= 0:
        kept -= 1
        room -= _char_cells(path[kept])
    return dots + path[kept:]


def wrap(text: str, width: int | None, indent: str = "") -> list[str]:
    """`text` as lines that fit `width`, each starting with `indent`. No width means one line."""
    if width is None:
        return [indent + text]
    return textwrap.wrap(text, max(20, width - 1), initial_indent=indent, subsequent_indent=indent,
                         break_on_hyphens=False) or [indent]
