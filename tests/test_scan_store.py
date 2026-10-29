import os
import sqlite3
from types import SimpleNamespace

import pytest

from spacetrail import scan as scan_module
from spacetrail.scan import scan
from spacetrail.store import Store


def write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_sizes_roll_up(tmp_path):
    write(tmp_path / "a" / "one.bin", 100)
    write(tmp_path / "a" / "b" / "two.bin", 50)
    write(tmp_path / "top.bin", 7)
    r = scan(tmp_path)
    assert r.files == 3
    assert r.sizes[str(tmp_path)] == 157
    assert r.sizes[str(tmp_path / "a")] == 150
    assert r.sizes[str(tmp_path / "a" / "b")] == 50


def test_depth_limit_folds_into_ancestor(tmp_path):
    write(tmp_path / "a" / "b" / "c" / "deep.bin", 30)
    r = scan(tmp_path, depth=1)
    assert str(tmp_path / "a" / "b") not in r.sizes
    assert r.sizes[str(tmp_path / "a")] == 30
    assert r.sizes[str(tmp_path)] == 30


def test_symlinked_folder_is_not_counted_twice(tmp_path):
    write(tmp_path / "real" / "data.bin", 40)
    try:
        os.symlink(tmp_path / "real", tmp_path / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return  # no symlink permission on this machine
    r = scan(tmp_path)
    assert r.sizes[str(tmp_path)] == 40


def test_store_roundtrip_and_prune(tmp_path):
    write(tmp_path / "data" / "f.bin", 10)
    store = Store(tmp_path / "db.sqlite")
    r = scan(tmp_path / "data")
    old = store.save(r, taken=1_000)
    new = store.save(r, taken=1_000 + 100 * 86400)
    assert [s.id for s in store.snapshots()] == [old.id, new.id]
    assert store.sizes(new.id)[r.root] == 10
    assert store.prune(keep_days=30, now=new.taken) == 1
    assert [s.id for s in store.snapshots()] == [new.id]
    store.close()


OLD_SCHEMA = """
CREATE TABLE snapshot (id INTEGER PRIMARY KEY, root TEXT NOT NULL, taken REAL NOT NULL,
    files INTEGER NOT NULL, disk_free INTEGER, disk_total INTEGER);
CREATE TABLE folder (snapshot INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
    path TEXT NOT NULL, size INTEGER NOT NULL, PRIMARY KEY (snapshot, path)) WITHOUT ROWID;
INSERT INTO snapshot VALUES (1, '/data', 1000, 3, NULL, NULL);
INSERT INTO folder VALUES (1, '/data', 99);
"""


def test_database_from_0_2_is_migrated_in_place(tmp_path):
    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(db)
    con.executescript(OLD_SCHEMA)
    con.close()
    store = Store(db)
    (old,) = store.snapshots()
    assert old.depth is None and store.sizes(old.id) == {"/data": 99}
    write(tmp_path / "data" / "f.bin", 10)
    new = store.save(scan(tmp_path / "data", depth=4))
    assert store.snapshots()[-1].depth == new.depth == 4
    store.close()


class FakeEntry:
    def __init__(self, attributes, tag=0):
        self._stat = SimpleNamespace(st_file_attributes=attributes, st_reparse_tag=tag)

    def is_symlink(self):
        return False

    def stat(self, follow_symlinks=True):
        return self._stat


@pytest.mark.parametrize("attributes, tag, is_link", [
    (0x10, 0, False),               # plain folder
    (0x410, 0xA000000C, True),      # symlink
    (0x410, 0xA0000003, True),      # junction
    (0x410, 0x9000601A, False),     # OneDrive placeholder folder
    (0x410, 0x9000001A, False),     # other cloud files tag
])
def test_only_symlinks_and_junctions_are_skipped(attributes, tag, is_link, monkeypatch):
    monkeypatch.setattr(scan_module.sys, "platform", "win32")
    assert scan_module._is_link(FakeEntry(attributes, tag)) is is_link
