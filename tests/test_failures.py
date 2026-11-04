"""What the CLI does when the disk, the database or the terminal misbehave."""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from types import SimpleNamespace

import pytest

from spacetrail import cli, schedule
from spacetrail import scan as scan_module
from spacetrail import store as store_module
from spacetrail.cli import main
from spacetrail.store import Store


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite"
    monkeypatch.setenv("SPACETRAIL_DB", str(path))
    return path


def grow(path, mb):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * mb * 1024 * 1024)


def test_reader_that_leaves_early_is_not_an_error(tmp_path, db):
    data = tmp_path / "data"
    grow(data / "sub" / "a.bin", 2)
    assert main(["snap", "--quiet", str(data)]) == 0
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    p = subprocess.Popen([sys.executable, "-m", "spacetrail", "top", str(data)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdout.close()  # what `spacetrail top | more` does when you quit more
    err = p.stderr.read()
    p.stderr.close()
    assert p.wait(timeout=60) == 0, err
    assert err == b""


@pytest.mark.parametrize("command", ["list", "report", "top", "snap"])
@pytest.mark.parametrize("damage", ["not_sqlite", "cut_off"])
def test_damaged_database_gets_a_message_not_a_traceback(command, damage, tmp_path, db, capsys):
    if damage == "not_sqlite":
        db.write_bytes(b"this is not a database " * 50)
    else:
        grow(tmp_path / "data" / "sub" / "a.bin", 2)
        assert main(["snap", "--quiet", str(tmp_path / "data")]) == 0
        db.write_bytes(db.read_bytes()[:5000])
    capsys.readouterr()
    assert main([command] + ([] if command == "list" else [str(tmp_path / "data")])) == 1
    err = capsys.readouterr().err
    assert str(db) in err and "damaged" in err


def test_database_location_that_cant_be_used(tmp_path, monkeypatch, capsys):
    (tmp_path / "file").write_text("x", encoding="utf-8")
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "file" / "db.sqlite"))
    assert main(["list"]) == 1
    assert "can't create" in capsys.readouterr().err
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path))  # a folder
    assert main(["list"]) == 1
    assert "can't use the snapshot database" in capsys.readouterr().err


def test_unschedule_works_with_a_damaged_database(db, monkeypatch, capsys):
    db.write_bytes(b"this is not a database " * 50)
    monkeypatch.setattr(schedule, "uninstall", lambda: "Removed.")
    assert main(["unschedule"]) == 0
    assert "Removed." in capsys.readouterr().out


def test_one_missing_folder_does_not_stop_the_others(tmp_path, db, capsys):
    data = tmp_path / "data"
    data.mkdir()
    assert main(["snap", str(tmp_path / "unplugged"), str(data)]) == 2
    captured = capsys.readouterr()
    assert "Not a folder" in captured.err and "Saved" in captured.out
    store = Store(db)
    assert store.roots() == [str(data)]
    store.close()


def test_unreadable_folder_saves_no_snapshot(tmp_path, db, monkeypatch, capsys):
    real = os.scandir

    def denied(path):
        if str(path) == str(tmp_path):
            raise PermissionError(13, "Permission denied")
        return real(path)

    monkeypatch.setattr(scan_module.os, "scandir", denied)
    assert main(["snap", str(tmp_path)]) == 2
    assert "Can't read" in capsys.readouterr().err
    store = Store(db)
    assert store.snapshots() == []
    store.close()


def test_json_first_run_reports_a_failed_snapshot(tmp_path, db, capsys):
    assert main(["report", "--json", str(tmp_path / "nope")]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Not a folder" in captured.err


def test_folder_name_that_is_not_valid_unicode(tmp_path, db, capsysbinary):
    data = tmp_path / "data"
    try:
        grow(data / "bad\udcffname" / "a.bin", 2)
    except (OSError, UnicodeError):
        pytest.skip("this file system refuses such a name")
    assert main(["snap", "--quiet", str(data)]) == 0
    assert main(["top", str(data)]) == 0
    assert b"bad\\udcffname" in capsysbinary.readouterr().out
    assert main(["top", str(data), "--json"]) == 0
    assert b"bad\\\\udcffname" in capsysbinary.readouterr().out
    assert main(["snap", str(data / "bad\udcffname")]) == 0  # as a root it's printed unescaped
    assert main(["top", str(data / "bad\udcffname")]) == 0
    assert b"Traceback" not in capsysbinary.readouterr().err


def _no_home(monkeypatch):
    def nowhere():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(store_module.Path, "home", nowhere)


def test_database_location_needs_no_home_folder_when_the_variable_is_set(tmp_path, monkeypatch):
    _no_home(monkeypatch)
    monkeypatch.delenv("SPACETRAIL_DB", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert store_module.default_db() == tmp_path / "spacetrail" / "snapshots.db"


def test_no_home_folder_and_no_variables(monkeypatch, capsys):
    _no_home(monkeypatch)
    for name in ("SPACETRAIL_DB", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    assert main(["list"]) == 1
    assert "SPACETRAIL_DB" in capsys.readouterr().err


def test_empty_variables_count_as_not_set(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module.Path, "home", lambda: tmp_path)
    for name in ("SPACETRAIL_DB", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.setenv(name, "")
    assert store_module.default_db().is_absolute()  # not ./spacetrail in the current folder


def test_schedule_refuses_a_missing_folder(tmp_path, db, monkeypatch, capsys):
    monkeypatch.setattr(schedule, "install", lambda *a: pytest.fail("must not install"))
    assert main(["schedule", str(tmp_path / "nope")]) == 2
    assert "Not a folder" in capsys.readouterr().err


def _fake_schtasks(monkeypatch, answers):
    """Answer each schtasks verb with (exit code, stderr)."""
    monkeypatch.setattr(schedule.sys, "platform", "win32")

    def run(cmd, **kw):
        code, err = answers[cmd[1]]
        return subprocess.CompletedProcess(cmd, code, "", err)

    monkeypatch.setattr(schedule.subprocess, "run", run)


def test_unschedule_without_a_task(monkeypatch):
    _fake_schtasks(monkeypatch, {"/Query": (1, "ERROR: not found")})
    assert schedule.uninstall() == "There was no daily task."


def test_unschedule_says_so_when_windows_refuses(db, monkeypatch, capsys):
    _fake_schtasks(monkeypatch, {"/Query": (0, ""), "/Delete": (1, "ERROR: Access is denied.")})
    assert main(["unschedule"]) == 1
    err = capsys.readouterr().err
    assert "Access is denied" in err and "no daily task" not in err


@pytest.mark.skipif(sys.platform != "win32", reason="the oem codec exists only on Windows")
def test_schtasks_output_with_umlauts_is_decoded(monkeypatch):
    # "ü" in code page 850. As cp1252 this byte has no character and used to end the command.
    script = "import sys; sys.stderr.buffer.write(b'F\\x81r den Task'); sys.exit(1)"
    r = schedule._capture([sys.executable, "-c", script])
    assert r.returncode == 1 and r.stderr.startswith("F") and r.stderr.endswith("r den Task")


def test_uninstall_without_crontab_installed(monkeypatch):
    monkeypatch.setattr(schedule.sys, "platform", "linux")
    monkeypatch.setattr(schedule.shutil, "which", lambda name: None)
    assert schedule.uninstall() == "There was no cron entry."


def test_cron_line_quotes_spaces_and_percent_signs():
    line = schedule._cron_line(["/home/me/My Files", "/data/100%"], "08:05")
    assert "'/home/me/My Files'" in line and "/data/100\\%" in line


def test_when_goes_by_the_calendar():
    def at(days_ago, hour, minute):
        day = datetime.now().date() - timedelta(days=days_ago)
        return datetime.combine(day, datetime_time(hour, minute)).timestamp()

    assert "(today)" in cli._when(at(0, 0, 1))
    assert "(yesterday)" in cli._when(at(1, 23, 59))  # under 24 hours ago on most of the day
    assert "(yesterday)" in cli._when(at(1, 0, 1))
    assert "(2 days ago)" in cli._when(at(2, 23, 59))


def test_progress_line_stays_on_one_row_of_a_narrow_terminal(monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "40")
    progress = cli._Progress("C:\\" + "long folder name\\" * 10 + "end", True)
    progress(5000)
    progress(1_234_000)
    err = capsys.readouterr().err
    assert all(len(frame) == 39 for frame in err.split("\r")[1:])
    assert "1,234,000 files" in err and "end" in err


def test_ctrl_c_wipes_the_progress_line(tmp_path, monkeypatch, capsys):
    def scan_then_ctrl_c(root, depth, progress):
        progress(5000)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan", scan_then_ctrl_c)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with pytest.raises(KeyboardInterrupt):
        cli._scan_with_progress(str(tmp_path), SimpleNamespace(quiet=False, depth=6))
    last_frame = capsys.readouterr().err.split("\r")[-2]
    assert last_frame.strip() == ""


def test_ctrl_c_exits_with_130(tmp_path, db, monkeypatch, capsys):
    def interrupted(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan", interrupted)
    assert main(["snap", str(tmp_path)]) == 130
    assert capsys.readouterr().err.strip() == "Stopped."
