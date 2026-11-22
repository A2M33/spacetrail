"""Print the spacetrail report shown in the README as plain text (escape codes removed).

    python tools/demo/make_demo.py
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "src"))

from spacetrail.scan import ScanResult  # noqa: E402
from spacetrail.store import Store  # noqa: E402


# Dark "trace" palette
GROUND = (0x0B, 0x12, 0x22)
PANEL = (0x11, 0x1A, 0x2D)
INSET = (0x18, 0x23, 0x3A)
LINE = (0x22, 0x30, 0x4B)
TRACE = (0x3A, 0x4D, 0x70)
INK = (0xE6, 0xED, 0xF7)
INK_2 = (0x93, 0xA3, 0xBD)
SIGNAL = (0x2F, 0xCB, 0xEA)
SIGNAL_INK = (0x7F, 0xE0, 0xF3)  # signal-coloured text
FAULT = (0xFF, 0x6B, 0x6B)
OK = (0x3F, 0xCF, 0x93)

ROOT = "X:\\"
MB, GB = 1024**2, 1024**3
# Folder: (size a week ago, size today). Parents get the sum of what's below them.
FOLDERS = {
    r"Program Files (x86)\Steam\steamapps\common\Hades II": (0, 2.3 * GB),
    r"Program Files (x86)\Steam\steamapps\common\Portal 2": (11.8 * GB, 11.8 * GB),
    r"Program Files (x86)\Steam\steamapps\downloading": (0, 290 * MB),
    r"Users\amin\Downloads": (210 * MB, 1.9 * GB),
    r"Users\amin\AppData\Local\Google\Chrome": (140 * MB, 750 * MB),
    r"Users\amin\AppData\Local\Temp\installer_tmp": (0, 380 * MB),
    r"Users\amin\Videos\Captures": (830 * MB, 0),
    r"Users\amin\Documents": (3.1 * GB, 3.1 * GB),
    r"Windows\SoftwareDistribution\Download": (0, 460 * MB),
    r"Windows\System32": (6.4 * GB, 6.4 * GB),
}
FREE_BEFORE, FREE_AFTER, TOTAL = 47.2 * GB, 42.1 * GB, 237 * GB


def snapshot(which: int) -> ScanResult:
    sizes = {ROOT: 0}
    for rel, pair in FOLDERS.items():
        n = int(pair[which])
        parts = rel.split("\\")
        sizes[ROOT] += n
        for k in range(1, len(parts) + 1):
            p = ROOT + "\\".join(parts[:k])
            sizes[p] = sizes.get(p, 0) + n
    return ScanResult(ROOT, sizes, files=412_000 + which * 9_000)


def capture() -> str:
    """Two snapshots, then the report exactly as spacetrail prints it."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "snapshots.db"
        now = time.time()
        store = Store(db)
        store.save(snapshot(0), disk=(int(FREE_BEFORE), int(TOTAL)), taken=now - 7 * 86400)
        store.save(snapshot(1), disk=(int(FREE_AFTER), int(TOTAL)), taken=now)
        store.close()
        env = {**os.environ, "SPACETRAIL_DB": str(db), "FORCE_COLOR": "1", "PYTHONPATH": str(REPO / "src")}
        env.pop("NO_COLOR", None)
        out = subprocess.run([sys.executable, "-m", "spacetrail", "report"], env=env, cwd=tmp,
                             capture_output=True, check=True).stdout
    return out.decode("utf-8").replace("\r\n", "\n").rstrip("\n")


out = ["PS> spacetrail", *capture().splitlines()]
ESC = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
lines = out.splitlines() if isinstance(out, str) else out
text = "\n".join(ESC.sub("", line).rstrip() for line in lines).rstrip()
sys.stdout.reconfigure(encoding="utf-8")
print(text)
