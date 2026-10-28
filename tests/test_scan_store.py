import os

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
