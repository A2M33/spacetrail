import sys

import pytest

from spacetrail import cli, schedule
from spacetrail.cli import main
from spacetrail.store import Store


def test_first_run_then_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data = tmp_path / "data"
    (data / "Downloads").mkdir(parents=True)

    assert main(["snap", str(data)]) == 0
    assert main(["report", str(data)]) == 0
    assert "only one snapshot" in capsys.readouterr().out

    (data / "Downloads" / "big.iso").write_bytes(b"x" * 3 * 1024 * 1024)
    assert main(["snap", str(data)]) == 0
    capsys.readouterr()
    assert main(["--since", "0", "--min", "1MB"]) == 0  # no subcommand means report
    out = capsys.readouterr().out
    assert "Downloads" in out and "+3.0 MB" in out


def test_task_xml_runs_at_given_time():
    xml = schedule._task_xml(["C:\\"], "08:05")
    assert "T08:05:00" in xml
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "snap --scheduled C:\\" in xml


def test_cron_line():
    line = schedule._cron_line(["/home/me"], "08:05")
    assert line.startswith("5 8 * * * ")
    assert line.endswith("snap --scheduled /home/me # spacetrail")


def test_snap_without_console_streams(tmp_path, monkeypatch):
    # pythonw.exe (the daily task) has no stdout or stderr at all.
    db = tmp_path / "db.sqlite"
    monkeypatch.setenv("SPACETRAIL_DB", str(db))
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert main(["snap", "--quiet", str(data)]) == 0
    assert main(["snap", str(data)]) == 0
    store = Store(db)
    assert len(store.snapshots()) == 2
    store.close()


def _grow(path, mb):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * mb * 1024 * 1024)


def test_report_unknown_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data, other = tmp_path / "data", tmp_path / "other"
    data.mkdir()
    other.mkdir()
    assert main(["snap", str(data)]) == 0
    capsys.readouterr()
    assert main(["report", str(other)]) == 1
    err = capsys.readouterr().err
    assert "No snapshots of" in err and str(data) in err


def test_report_drills_into_subfolder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data = tmp_path / "data"
    (data / "a").mkdir(parents=True)
    (data / "b").mkdir()
    assert main(["snap", str(data)]) == 0
    _grow(data / "a" / "sub" / "big.bin", 3)
    _grow(data / "b" / "other.bin", 2)
    assert main(["snap", str(data)]) == 0
    capsys.readouterr()
    assert main(["report", str(data / "a"), "--since", "0", "--min", "1MB"]) == 0
    out = capsys.readouterr().out
    assert str(data / "a") in out and "sub" in out and "+3.0 MB" in out
    assert "+2.0 MB" not in out and "+5.0 MB" not in out


@pytest.mark.skipif(sys.platform != "win32", reason="paths are case-sensitive here")
def test_report_path_ignores_case_on_windows(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data = tmp_path / "data"
    data.mkdir()
    assert main(["snap", str(data)]) == 0
    _grow(data / "dl" / "big.bin", 3)
    assert main(["snap", str(data).upper()]) == 0
    capsys.readouterr()
    assert main(["report", str(data).lower(), "--since", "0", "--min", "1MB"]) == 0
    out = capsys.readouterr().out
    assert "only one snapshot" not in out and "+3.0 MB" in out


@pytest.mark.parametrize("argv, flag", [
    (["report", "--min", "abc"], "--min"),
    (["report", "--since", "1y"], "--since"),
    (["report", "--min", "-5MB"], "--min"),
    (["report", "--top", "0"], "--top"),
    (["snap", "--depth", "-1"], "--depth"),
    (["schedule", "--time", "25:00"], "--time"),
    (["schedule", "--time", "noon"], "--time"),
])
def test_bad_arguments_give_a_short_error(argv, flag, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert flag in err and "Traceback" not in err


def test_schedule_time_is_normalized():
    assert schedule.parse_time("9:5") == "09:05"
    assert "T09:05:00" in schedule._task_xml(["C:\\"], schedule.parse_time("9:5"))


def test_schtasks_failure_shows_its_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    monkeypatch.setattr(schedule.sys, "platform", "win32")

    def fake_run(cmd, **kw):
        return schedule.subprocess.CompletedProcess(cmd, 1, "", "ERROR: Access is denied.\n")

    monkeypatch.setattr(schedule.subprocess, "run", fake_run)
    assert main(["schedule", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "Access is denied" in err and "Traceback" not in err


@pytest.mark.parametrize("flag, console_is_ours, hidden", [
    ("--quiet", False, False),     # typed in a terminal: leave the terminal alone
    ("--quiet", True, True),       # a daily task from 0.2.x
    ("--scheduled", False, True),  # a daily task from now on
])
def test_only_scheduled_runs_hide_the_console(flag, console_is_ours, hidden, tmp_path, monkeypatch):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    calls = []
    monkeypatch.setattr(cli, "_console_is_ours", lambda: console_is_ours)
    monkeypatch.setattr(cli, "_hide_console", lambda: calls.append("hide"))
    monkeypatch.setattr(cli, "_pause_if_double_clicked", lambda: calls.append("pause"))
    assert main(["snap", flag, str(tmp_path)]) == 0
    assert calls == (["hide"] if hidden else ["pause"])


def test_double_clicked_exe_shows_error_before_pausing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    seen = []

    def boom(args, store):
        raise ValueError("boom")

    monkeypatch.setattr(cli, "cmd_list", boom)
    monkeypatch.setattr(cli, "_console_is_ours", lambda: True)
    monkeypatch.setattr(cli, "_pause_if_double_clicked", lambda: seen.append(capsys.readouterr().err))
    assert main(["list"]) == 1
    assert len(seen) == 1 and "ValueError: boom" in seen[0]
