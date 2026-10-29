"""Command line: `spacetrail` (report), `snap`, `list`, `schedule`, `unschedule`."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime

from . import __version__, schedule
from .report import Change, changes, culprits, human, parse_days, parse_size, pick_baseline
from .scan import scan
from .store import Store, default_db, is_within, path_key


def default_root() -> str:
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return os.path.expanduser("~")


# ---------- output helpers ----------

class Style:
    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def bold(self, t): return self._wrap("1", t)
    def dim(self, t): return self._wrap("2", t)
    def red(self, t): return self._wrap("31", t)
    def green(self, t): return self._wrap("32", t)
    def yellow(self, t): return self._wrap("33", t)


def _style() -> Style:
    if os.environ.get("FORCE_COLOR"):
        return Style(True)
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return Style(False)
    if sys.platform == "win32":
        # Old Windows consoles need ANSI colours switched on explicitly.
        try:
            import ctypes

            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            return Style(False)
    return Style(True)


def _when(ts: float) -> str:
    d = datetime.fromtimestamp(ts)
    days = (time.time() - ts) / 86400
    ago = "today" if days < 1 else "yesterday" if days < 2 else f"{days:.0f} days ago"
    return f"{d:%b %d, %H:%M} ({ago})"


def _short(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return root if rel == "." else rel


def _rebase(sizes: dict[str, int], old_root: str, new_root: str) -> dict[str, int]:
    # Two snapshots of C:\Users and c:\users: spell the old paths like the new ones.
    if old_root == new_root:
        return sizes
    return {new_root + p[len(old_root):]: n for p, n in sizes.items()}


def _bar_char() -> str:
    # Some consoles and redirected output can't encode the block character.
    try:
        "█".encode(sys.stdout.encoding or "ascii")
        return "█"
    except (UnicodeEncodeError, LookupError):
        return "#"


def _bar(value: int, biggest: int, width: int = 20) -> str:
    n = max(1, round(width * value / biggest)) if biggest else 0
    return _bar_char() * n + " " * (width - n)


def _print_rows(rows: list[Change], root: str, s: Style, growing: bool) -> None:
    biggest = max(abs(c.delta) for c in rows)
    for c in rows:
        size = human(c.delta, signed=True).rjust(11)
        # Folders under 1 MB aren't stored, so 0 really means "less than 1 MB".
        before = human(c.before) if c.before else "<1 MB"
        after = human(c.after) if c.after else "<1 MB"
        color = s.red if growing else s.green
        print(f"  {color(size)}  {s.dim(_bar(abs(c.delta), biggest))}  {_short(c.path, root)}"
              f"  {s.dim(f'{before} -> {after}')}")


# ---------- commands ----------

def cmd_snap(args, store: Store) -> int:
    s = _style()
    for root in args.paths or [default_root()]:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            print(f"Not a folder: {root}", file=sys.stderr)
            return 2
        show = not args.quiet and sys.stderr.isatty()
        started = time.monotonic()

        def progress(files: int) -> None:
            if show:
                print(f"\r  scanning {root}  {files:,} files", end="", file=sys.stderr, flush=True)

        result = scan(root, depth=args.depth, progress=progress)
        if show:
            print("\r" + " " * 70 + "\r", end="", file=sys.stderr)
        usage = shutil.disk_usage(root)
        store.save(result, disk=(usage.free, usage.total))
        store.prune(args.keep)
        if not args.quiet:
            took = time.monotonic() - started
            print(f"{s.green('Saved')} {root}: {human(result.sizes[root])} in {result.files:,} files "
                  f"({took:.0f}s, {result.skipped} folders not readable)")
    return 0


def cmd_report(args, store: Store) -> int:
    s = _style()
    if getattr(args, "fresh", False):
        cmd_snap(argparse.Namespace(paths=[args.path] if args.path else [], depth=args.depth,
                                    keep=args.keep, quiet=False), store)
    if not store.roots():
        root = os.path.abspath(args.path) if args.path else default_root()
        print(f"No snapshots yet. Taking the first one of {root} now...\n")
        cmd_snap(argparse.Namespace(paths=[root], depth=args.depth, keep=args.keep, quiet=False), store)
        print("\nThat's the starting point. To see what grows, take another snapshot later,\n"
              "or let spacetrail do it daily:  spacetrail schedule")
        return 0

    if args.path:
        focus = os.path.abspath(args.path)
        root = store.root_for(focus)
        if root is None:
            print(f"No snapshots of {focus} yet. Take one with:  spacetrail snap \"{focus}\"\n"
                  f"Folders with snapshots: {', '.join(store.roots())}", file=sys.stderr)
            return 1
        targets = [(root, focus)]
    else:
        targets = [(root, root) for root in store.roots()]

    days, min_bytes = parse_days(args.since), parse_size(args.min)
    for root, focus in targets:
        pair = pick_baseline(store.snapshots(root), days)
        if pair is None:
            print(f"{s.bold(root)}: only one snapshot so far. Run `spacetrail snap` again later "
                  "or `spacetrail schedule`.")
            continue
        old, new = pair
        before = _rebase(store.sizes(old.id), old.root, new.root)
        after = store.sizes(new.id)
        # `report C:\Users\me` drills into a snapshot of C:\ and shows only what's below it.
        shown = next((p for d in (after, before) for p in d if path_key(p) == path_key(focus)), None)
        if shown is None:
            print(f"{s.bold(focus)}: not in the snapshots of {root}. spacetrail only remembers folders "
                  "over 1 MB, a few levels deep (see --depth).")
            continue
        before = {p: n for p, n in before.items() if is_within(p, shown)}
        after = {p: n for p, n in after.items() if is_within(p, shown)}
        ch = changes(before, after)
        ch.pop(shown, None)  # the total is already in the header line
        print(s.bold(shown) + s.dim(f"   {_when(old.taken)}  ->  {_when(new.taken)}"))
        new_size = after.get(shown, 0)
        total = new_size - before.get(shown, 0)
        line = f"  folder size {human(new_size)} ({human(total, signed=True)})"
        if old.disk_free is not None and new.disk_free is not None:
            line += f"   free space {human(old.disk_free)} -> {human(new.disk_free)}"
        print(line + "\n")

        grew = culprits(ch, min_bytes, args.top, growing=True)
        shrank = culprits(ch, min_bytes, args.top, growing=False)
        if grew:
            print(s.yellow("  Grew"))
            _print_rows(grew, shown, s, growing=True)
        if shrank:
            print(("\n" if grew else "") + s.yellow("  Shrank"))
            _print_rows(shrank, shown, s, growing=False)
        if not grew and not shrank:
            print(f"  Nothing changed by more than {human(min_bytes)}.")
        print()
    return 0


def cmd_list(args, store: Store) -> int:
    snaps = store.snapshots()
    if not snaps:
        print("No snapshots yet. Run: spacetrail snap")
        return 0
    for snap in snaps:
        size = store.sizes(snap.id).get(snap.root, 0)
        print(f"{_when(snap.taken):32} {snap.root:20} {human(size):>10}  {snap.files:>10,} files")
    print(f"\nDatabase: {default_db()}")
    return 0


def cmd_schedule(args, store: Store) -> int:
    paths = [os.path.abspath(p) for p in args.paths] or [default_root()]
    print(schedule.install(paths, args.time))
    return 0


def cmd_unschedule(args, store: Store) -> int:
    print(schedule.uninstall())
    return 0


def _fix_streams() -> None:
    # pythonw.exe (the daily task) starts us with no console at all: sys.stdout and
    # sys.stderr are None, and the first print would crash the snapshot.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    enc = getattr(sys.stdout, "encoding", None)
    if enc and enc.lower() not in ("utf-8", "utf8") and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _fix_streams()

    p = argparse.ArgumentParser(
        prog="spacetrail",
        description="See which folders ate your disk space. Takes daily snapshots and compares them.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--depth", type=int, default=6, help="how many folder levels to remember (default 6)")
        sp.add_argument("--keep", type=float, default=90, help="days of snapshots to keep (default 90)")

    rp = sub.add_parser("report", help="show what grew (default command)")
    rp.add_argument("path", nargs="?", help="only this snapshot root")
    rp.add_argument("--since", default="7d", help="compare with this long ago: 12h, 3d, 2w (default 7d)")
    rp.add_argument("--min", default="100MB", help="ignore changes smaller than this (default 100MB)")
    rp.add_argument("--top", type=int, default=12, help="rows per list (default 12)")
    rp.add_argument("--fresh", action="store_true", help="take a new snapshot first")
    common(rp)

    sp = sub.add_parser("snap", help="take a snapshot now")
    sp.add_argument("paths", nargs="*", help=f"folders to scan (default {default_root()})")
    sp.add_argument("--quiet", action="store_true")
    common(sp)

    sub.add_parser("list", help="list saved snapshots")

    sc = sub.add_parser("schedule", help="take a snapshot automatically every day")
    sc.add_argument("paths", nargs="*", help=f"folders to scan (default {default_root()})")
    sc.add_argument("--time", default="12:30", help="time of day, HH:MM (default 12:30)")

    sub.add_parser("unschedule", help="remove the daily snapshot")

    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version"):
        argv = ["report", *argv]
    args = p.parse_args(argv)

    handlers = {"report": cmd_report, "snap": cmd_snap, "list": cmd_list,
                "schedule": cmd_schedule, "unschedule": cmd_unschedule}
    if args.cmd == "snap" and args.quiet:
        _hide_console()
    store = Store()
    try:
        return handlers[args.cmd](args, store)
    except KeyboardInterrupt:
        return 130
    finally:
        store.close()
        _pause_if_double_clicked()


def _is_windows_exe() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _hide_console() -> None:
    # The daily task starts spacetrail.exe in its own console; hide it right away.
    if _is_windows_exe():
        import ctypes

        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)


def _pause_if_double_clicked() -> None:
    # Double-clicking spacetrail.exe opens a console that closes as soon as we return.
    # If we're the only process attached to it, nobody started us from a terminal.
    if not _is_windows_exe():
        return
    import ctypes

    procs = (ctypes.c_uint32 * 2)()
    if ctypes.windll.kernel32.GetConsoleProcessList(procs, 2) == 1:
        input("\nPress Enter to close.")
