from file_organizer.conflicts import resolve_conflict
from file_organizer.models import ConflictStrategy


def test_no_collision_passthrough(tmp_path):
    dst = tmp_path / "a.jpg"
    final, backup = resolve_conflict(dst, ConflictStrategy.RENAME)
    assert final == dst
    assert backup is None


def test_rename_increments(tmp_path):
    dst = tmp_path / "a.jpg"
    dst.write_bytes(b"x")
    final, backup = resolve_conflict(dst, ConflictStrategy.RENAME)
    assert final.name == "a (1).jpg"
    assert backup is None
    # create that one too
    final.write_bytes(b"y")
    final2, _ = resolve_conflict(dst, ConflictStrategy.RENAME)
    assert final2.name == "a (2).jpg"


def test_skip_returns_none(tmp_path):
    dst = tmp_path / "a.jpg"
    dst.write_bytes(b"x")
    final, backup = resolve_conflict(dst, ConflictStrategy.SKIP)
    assert final is None
    assert backup is None


def test_overwrite_backup_path(tmp_path):
    dst = tmp_path / "a.jpg"
    dst.write_bytes(b"x")
    final, backup = resolve_conflict(dst, ConflictStrategy.OVERWRITE)
    assert final == dst
    assert backup is not None
    assert ".bak-" in backup.name
    assert backup.name.startswith("a.jpg.bak-")
