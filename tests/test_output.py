"""Lines must fit the terminal, and pipes must keep getting whole lines."""

import os

import pytest

from spacetrail import cli
from spacetrail.cli import main
from spacetrail.output import cells, fit_path, wrap
from spacetrail.report import Change

ROOT = os.path.abspath("root")
MB = 1024**2


def rows():
    return [
        Change(os.path.join(ROOT, "a", "long", "path", "that", "keeps", "going", "and", "going", "node_modules"),
               300 * MB, 2 * MB, 302 * MB),
        Change(os.path.join(ROOT, "Downloads"), 100 * MB, 0, 100 * MB),
    ]


def test_cells_counts_terminal_columns():
    assert cells("abc") == 3
    assert cells("日本") == 4
    assert cells("می\u200cخواهم") == 7  # the zero-width non-joiner takes no column
    assert cells("e\u0301") == 1  # e and a combining accent


def test_fit_path_keeps_the_end_of_the_path():
    assert fit_path("short", 10) == "short"
    assert fit_path(r"C:\Users\me\Downloads", 12) == "…e\\Downloads"[-12:]
    assert fit_path("日本語のフォルダ", 7) == "…ォルダ"
    assert cells(fit_path("日本語のフォルダ", 8)) <= 8


def test_wrap_without_a_width_leaves_one_line():
    text = "word " * 40
    assert wrap(text, None, "  ") == ["  " + text]
    lines = wrap(text, 40, "  ")
    assert len(lines) > 1 and all(len(line) < 40 and line.startswith("  ") for line in lines)


@pytest.mark.parametrize("width, has_bar, has_sizes", [
    (120, True, True), (80, True, True), (60, True, False), (40, False, False),
])
def test_rows_fit_the_terminal(width, has_bar, has_sizes, monkeypatch, capsys):
    monkeypatch.setattr(cli, "terminal_width", lambda: width)
    monkeypatch.setattr(cli, "hint", lambda path: "Some tip that is long enough to need wrapping. " * 3)
    cli._print_rows(rows(), ROOT, cli.Style(False), growing=True)
    out = capsys.readouterr().out
    assert all(cells(line) < width for line in out.splitlines())
    assert "node_modules" in out and "+300.0 MB" in out
    assert ("-> 302.0 MB" in out) is has_sizes
    assert ("█" in out or "#" in out) is has_bar


def test_piped_rows_keep_the_whole_path(monkeypatch, capsys):
    monkeypatch.setattr(cli, "terminal_width", lambda: None)
    cli._print_rows(rows(), ROOT, cli.Style(False), growing=False)
    assert os.path.relpath(rows()[0].path, ROOT) in capsys.readouterr().out


@pytest.mark.parametrize("growing", [True, False])
def test_only_growth_is_amber(growing, monkeypatch, capsys):
    monkeypatch.setattr(cli, "terminal_width", lambda: None)
    cli._print_rows(rows(), ROOT, cli.Style(True), growing=growing)
    out = capsys.readouterr().out
    assert ("\033[38;5;214m +300.0 MB" in out) is growing
    assert "\033[2m" in out  # the sizes column is a dim label either way
    assert not any(f"\033[{code}m" in out for code in ("31", "32", "33"))  # no red, green or yellow


def test_tip_sits_under_the_row(monkeypatch, capsys):
    monkeypatch.setattr(cli, "hint", lambda path: "A tip.")
    cli._print_rows(rows()[:1], ROOT, cli.Style(False), growing=True)
    assert capsys.readouterr().out.splitlines()[1] == " " * cli.HINT_INDENT + "A tip."


def test_heading_moves_details_to_a_second_line_when_narrow(monkeypatch, capsys):
    monkeypatch.setattr(cli, "terminal_width", lambda: 50)
    cli._print_heading("C:\\" + "folder\\" * 4, "Nov 01, 10:00 (3 days ago)  ->  Nov 04, 10:00 (today)", cli.Style(False))
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) >= 2 and all(cells(line) < 50 for line in lines)


def test_saved_line_counts_in_good_english(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data = tmp_path / "data"
    data.mkdir()
    (data / "one.bin").write_bytes(b"x")
    assert main(["snap", str(data)]) == 0
    out = capsys.readouterr().out
    assert "in 1 file (" in out and "not readable" not in out


def test_list_puts_a_long_root_last(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPACETRAIL_DB", str(tmp_path / "db.sqlite"))
    data = tmp_path / ("x" * 60)
    data.mkdir()
    (data / "one.bin").write_bytes(b"x")
    assert main(["snap", "--quiet", str(data)]) == 0
    assert main(["list"]) == 0
    line = capsys.readouterr().out.splitlines()[0]
    assert line.endswith(str(data)) and "1 B" in line and "1 file" in line
