"""Run `spacetrail snap` once a day: Task Scheduler on Windows, cron elsewhere."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK = "spacetrail"
CRON_TAG = "# spacetrail"


def _python() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable  # the standalone spacetrail.exe
    # pythonw.exe runs without opening a console window every day.
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return str(quiet if sys.platform == "win32" and quiet.exists() else exe)


def _args(paths: list[str]) -> list[str]:
    prefix = [] if getattr(sys, "frozen", False) else ["-m", "spacetrail"]
    return [*prefix, "snap", "--quiet", *paths]


def _task_xml(paths: list[str], time: str) -> str:
    args = " ".join(f'"{a}"' if " " in a else a for a in _args(paths))
    # XML instead of plain schtasks flags, because only XML can set StartWhenAvailable:
    # if the PC was off at the scheduled time, Windows runs the task once it's back on.
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Daily folder size snapshot for spacetrail</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{time}:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <StartWhenAvailable>true</StartWhenAvailable>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Priority>9</Priority>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec><Command>{escape(_python())}</Command><Arguments>{escape(args)}</Arguments></Exec>
  </Actions>
</Task>
"""


def install(paths: list[str], time: str = "12:30") -> str:
    if sys.platform == "win32":
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
            f.write(_task_xml(paths, time))
        try:
            subprocess.run(
                ["schtasks", "/Create", "/TN", TASK, "/XML", f.name, "/F"],
                check=True, capture_output=True, text=True,
            )
        finally:
            os.unlink(f.name)
        return f"Windows Task Scheduler will take a snapshot every day at {time} (task name: {TASK})."

    if not shutil.which("crontab"):
        raise RuntimeError("crontab not found. Add this to your scheduler by hand:\n" + _cron_line(paths, time))
    lines = [line for line in _crontab() if CRON_TAG not in line]
    lines.append(_cron_line(paths, time))
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    return f"cron will take a snapshot every day at {time}."


def uninstall() -> str:
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True, text=True)
        return "Removed the daily task." if r.returncode == 0 else "There was no daily task."
    lines = _crontab()
    kept = [line for line in lines if CRON_TAG not in line]
    if len(kept) == len(lines):
        return "There was no cron entry."
    subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, check=True)
    return "Removed the cron entry."


def _cron_line(paths: list[str], time: str) -> str:
    hour, minute = time.split(":")
    cmd = " ".join([_python(), *_args(paths)])
    return f"{int(minute)} {int(hour)} * * * {cmd} {CRON_TAG}"


def _crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []
