"""What the CLI does when the disk, the database or the terminal misbehave."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from spacetrail import cli, schedule
from spacetrail import scan as scan_module
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


def test_ctrl_c_exits_with_130(tmp_path, db, monkeypatch, capsys):
    def interrupted(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan", interrupted)
    assert main(["snap", str(tmp_path)]) == 130
    assert capsys.readouterr().err.strip() == "Stopped."
