import sys

from spacetrail import schedule
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
    assert "snap --quiet C:\\" in xml


def test_cron_line():
    line = schedule._cron_line(["/home/me"], "08:05")
    assert line.startswith("5 8 * * * ")
    assert line.endswith("snap --quiet /home/me # spacetrail")


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
