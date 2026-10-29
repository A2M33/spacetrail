"""One-line notes on folders that are known to fill disks. spacetrail never deletes anything itself."""

from __future__ import annotations

import os
import tempfile

BROWSER = ("Browser data, mostly cache. In the browser: Settings > Privacy > "
           "Clear browsing data > Cached images and files.")

# Each rule: path endings (lowercase, "/" separators) and the note for that folder and
# anything inside it.
RULES: list[tuple[tuple[str, ...], str]] = [
    (("/$recycle.bin",),
     "Recycle Bin. Right-click its desktop icon > Empty Recycle Bin."),
    (("/windows/softwaredistribution/download",),
     "Windows Update downloads. Disk Cleanup > Clean up system files > Windows Update Cleanup."),
    (("/appdata/local/temp", "/windows/temp"),
     "Temporary files. Settings > System > Storage > Temporary files, or delete what's over a week old."),
    (("/node_modules",),
     "npm packages. Delete it in projects you're done with; `npm install` brings it back."),
    (("/pip/cache", "/.cache/pip", "/library/caches/pip"),
     "pip's download cache. `pip cache purge` empties it."),
    (("/npm-cache", "/.npm"),
     "npm's download cache. `npm cache clean --force` empties it."),
    (("/appdata/local/google/chrome", "/appdata/local/microsoft/edge", "/appdata/local/bravesoftware",
      "/appdata/local/mozilla/firefox", "/.cache/google-chrome", "/.cache/chromium", "/.cache/mozilla",
      "/library/caches/google", "/library/caches/firefox"),
     BROWSER),
]

TEMP_NOTE = RULES[2][1]


def _norm(path: str) -> str:
    return "/" + path.replace("\\", "/").strip("/").lower()


def _where(p: str, ending: str) -> int:
    """Where `ending` ends in `p` as whole folder names, or -1."""
    if p.endswith(ending):
        return len(p)
    i = p.rfind(ending + "/")
    return i + len(ending) if i >= 0 else -1


def temp_dir() -> str:
    return os.path.abspath(tempfile.gettempdir())  # %TEMP% on Windows, /tmp elsewhere


def hint(path: str) -> str | None:
    """How to reclaim space in `path`, if it's a folder we know about.

    The match closest to the end wins: node_modules inside Temp is about npm.
    """
    p, temp = _norm(path), _norm(temp_dir())
    best, note = (len(temp), TEMP_NOTE) if p == temp or p.startswith(temp + "/") else (-1, None)
    for endings, text in RULES:
        for e in endings:
            at = _where(p, e)
            if at > best:
                best, note = at, text
    return note
