"""Render docs/demo.png: the real `spacetrail` report over a made-up drive, in the A2M33 palette.

Two synthetic snapshots of X:\\ a week apart go into a throwaway database, then spacetrail
itself prints the report with colours forced on. The ANSI output is drawn as it comes:
amber (214) becomes the amber token, dim becomes the label grey, bold becomes Consolas Bold.
Windows only as written (Consolas from C:/Windows/Fonts).

    pip install pillow
    python tools/demo/make_demo.py
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "docs" / "demo.png"
sys.path.insert(0, str(REPO / "src"))

from spacetrail.scan import ScanResult  # noqa: E402
from spacetrail.store import Store  # noqa: E402

MONO = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
MONO_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 15)
LABEL = ImageFont.truetype(str(HERE / "fonts" / "Barlow-Medium.woff2"), 16)

# Light values from tokens.css
CAB = (0xE3, 0xE5, 0xE0)
PANEL = (0xF4, 0xF5, 0xF2)
INSET = (0xD5, 0xD9, 0xD3)
LINE = (0xB9, 0xBF, 0xB7)
INK = (0x1D, 0x24, 0x20)
INK_2 = (0x56, 0x60, 0x5A)
AMBER = (0xD9, 0x92, 0x11)
AMBER_INK = (0x6B, 0x46, 0x00)  # amber text that stays readable on the light panel

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


SGR = re.compile("\x1b\\[([0-9;]*)m")


def spans(line: str):
    """(text, colour, bold) pieces of one line of ANSI output."""
    colour, bold, pos = INK, False, 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            yield line[pos:m.start()], colour, bold
        code = m.group(1)
        if code in ("", "0"):
            colour, bold = INK, False
        elif code == "1":
            bold = True
        elif code == "2":
            colour = INK_2
        elif code == "38;5;214":
            colour = AMBER
        else:
            raise ValueError(f"no palette colour for SGR {code!r}")
        pos = m.end()
    if pos < len(line):
        yield line[pos:], colour, bold


def lamp_image(colour, size=12, scale=8):
    """An anti-aliased round lamp (drawn large, scaled down)."""
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=colour, outline=colour, width=scale)
    return big.resize((size, size), Image.LANCZOS)


def render(lines: list[str]) -> Image.Image:
    lh, margin, pad, bar = 24, 20, 26, 40
    cw = MONO.getlength("M")
    cols = max(len(SGR.sub("", line)) for line in lines)
    w = max(1200, int(margin * 2 + pad * 2 + cols * cw))
    h = margin * 2 + bar + pad + len(lines) * lh + pad - 6
    img = Image.new("RGB", (w, h), CAB)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((margin, margin, w - margin - 1, h - margin - 1), radius=6, fill=PANEL, outline=LINE)
    y_mid = margin + bar // 2
    x0 = margin + pad
    lamp = lamp_image(AMBER)  # amber: the drive grew
    img.paste(lamp, (x0, y_mid - 6), lamp)
    d.text((x0 + 22, y_mid), "spacetrail", font=LABEL, fill=INK_2, anchor="lm")
    d.line((margin + 1, margin + bar, w - margin - 2, margin + bar), fill=LINE)
    top = margin + bar + pad - 4
    for r, line in enumerate(lines):
        x, y = x0, top + r * lh
        for text, colour, bold in spans(line):
            font = MONO_BOLD if bold else MONO
            if colour == AMBER and text.strip("█ ") == "":  # the bar: amber blocks
                n = len(text.rstrip())
                d.rectangle((x, y + 3, x + n * cw - 1, y + lh - 6), fill=AMBER)
            elif colour == INK_2 and text.strip("█ ") == "" and "█" in text:  # a dim bar
                n = len(text.rstrip())
                d.rectangle((x, y + 3, x + n * cw - 1, y + lh - 6), fill=LINE)
            else:
                d.text((x, y), text, font=font, fill=AMBER_INK if colour == AMBER else colour)
            x += len(text) * cw
    return img


lines = ["PS> spacetrail", *capture().splitlines()]
lines[0] = "\x1b[1m" + lines[0] + "\x1b[0m"
img = render(lines)
img.save(OUT, optimize=True)
print(OUT, img.size)
