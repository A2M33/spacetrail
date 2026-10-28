from spacetrail.report import changes, culprits, human, parse_days, parse_size, pick_baseline
from spacetrail.store import Snapshot

GB = 1024**3


def snap(i, days):
    return Snapshot(i, "C:\\", days * 86400, 0, None, None)


def test_pick_baseline():
    snaps = [snap(1, 0), snap(2, 5), snap(3, 9), snap(4, 14)]
    old, new = pick_baseline(snaps, days=7)
    assert (old.id, new.id) == (2, 4)  # newest one at least a week before the latest
    old, new = pick_baseline(snaps, days=30)
    assert old.id == 1  # not that much history yet: use the oldest
    assert pick_baseline(snaps[:1], 7) is None


def test_child_that_explains_growth_replaces_parent():
    before = {"/": 10 * GB, "/home": 5 * GB, "/home/dl": 1 * GB}
    after = {"/": 19 * GB, "/home": 14 * GB, "/home/dl": 10 * GB}
    picked = culprits(changes(before, after), min_bytes=100 * 1024**2, limit=10)
    assert [c.path for c in picked] == ["/home/dl"]


def test_growth_spread_over_children_keeps_parent():
    before = {"/": 0, "/a": 0, "/a/x": 0, "/a/y": 0}
    after = {"/": 4 * GB, "/a": 4 * GB, "/a/x": 2 * GB, "/a/y": 2 * GB}
    picked = culprits(changes(before, after), min_bytes=GB, limit=10)
    assert {c.path for c in picked} == {"/a", "/a/x", "/a/y"}
    assert picked[0].path == "/a"


def test_shrinking_and_new_or_gone():
    before = {"/": 5 * GB, "/old": 5 * GB}
    after = {"/": 2 * GB, "/new": 2 * GB}
    ch = changes(before, after)
    shrunk = culprits(ch, min_bytes=GB, limit=10, growing=False)
    assert [c.path for c in shrunk] == ["/old"]
    assert shrunk[0].after == 0
    grown = culprits(ch, min_bytes=GB, limit=10)
    assert [c.path for c in grown] == ["/new"] and grown[0].before == 0


def test_small_changes_are_ignored():
    picked = culprits(changes({"/": 0}, {"/": 5}), min_bytes=1024, limit=10)
    assert picked == []


def test_formatting_and_parsing():
    assert human(0) == "0 B"
    assert human(1536) == "1.5 KB"
    assert human(3 * GB, signed=True) == "+3.0 GB"
    assert human(-GB // 2, signed=True) == "-512.0 MB"
    assert parse_size("500MB") == 500 * 1024**2
    assert parse_size("1.5gb") == int(1.5 * GB)
    assert parse_size("200") == 200 * 1024**2
    assert parse_days("2w") == 14
    assert parse_days("12h") == 0.5
    assert parse_days("3") == 3
