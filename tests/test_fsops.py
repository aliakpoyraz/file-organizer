import os
import stat
import sys

import pytest

from file_organizer import fsops
from file_organizer.errors import MoveError, PermissionDeniedError


def test_atomic_move_success(tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello world")
    dst = tmp_path / "out" / "dst.txt"
    fsops.atomic_move(src, dst, verify_hash=True)
    assert not src.exists()
    assert dst.read_bytes() == b"hello world"
    # no leftover .part
    assert not (dst.parent / (dst.name + ".part")).exists()


def test_atomic_move_cross_dir(tmp_path):
    src = tmp_path / "a" / "s.bin"
    src.parent.mkdir()
    src.write_bytes(b"data")
    dst = tmp_path / "b" / "c" / "s.bin"
    fsops.atomic_move(src, dst)
    assert dst.exists()
    assert not src.exists()


def test_hash_verify_mismatch_leaves_original(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_bytes(b"original")
    dst = tmp_path / "dst.txt"

    real_hash = fsops.file_hash
    calls = {"n": 0}

    def fake_hash(path, algo="sha256", chunk=1 << 20):
        calls["n"] += 1
        # Return different values for tmp vs src to force mismatch
        return real_hash(path) + ("A" if calls["n"] % 2 == 0 else "B")

    monkeypatch.setattr(fsops, "file_hash", fake_hash)
    with pytest.raises(MoveError):
        fsops.atomic_move(src, dst, verify_hash=True)
    # original intact, no dst, no .part
    assert src.read_bytes() == b"original"
    assert not dst.exists()
    assert not (dst.parent / (dst.name + ".part")).exists()


def test_part_cleanup_on_copy_failure(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_bytes(b"data")
    dst = tmp_path / "dst.txt"

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(fsops.shutil, "copy2", boom)
    with pytest.raises(MoveError):
        fsops.atomic_move(src, dst)
    assert src.exists()
    assert not (dst.parent / (dst.name + ".part")).exists()


def test_ensure_dest_writable_creates(tmp_path):
    d = tmp_path / "new" / "deep"
    fsops.ensure_dest_writable(d)
    assert d.is_dir()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permissions")
def test_ensure_dest_writable_readonly(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, 0o500)
    try:
        with pytest.raises(PermissionDeniedError):
            fsops.ensure_dest_writable(ro / "sub")
    finally:
        os.chmod(ro, 0o700)


def test_unique_path(tmp_path):
    p = tmp_path / "foo.jpg"
    assert fsops.unique_path(p) == p
    p.write_bytes(b"x")
    assert fsops.unique_path(p).name == "foo (1).jpg"


def test_stat_symlink_no_follow(tmp_path):
    target = tmp_path / "t.dat"
    target.write_bytes(b"abc")
    link = tmp_path / "l.jpg"
    link.symlink_to(target)
    fi = fsops.stat_file(link, follow_symlinks=False)
    assert fi.is_symlink is True
    fi2 = fsops.stat_file(link, follow_symlinks=True)
    assert fi2.is_symlink is True
    assert fi2.size == 3


def test_scan_no_recursive_skips_dirs(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"y")
    names = {fi.path.name for fi in fsops.scan(tmp_path, recursive=False)}
    assert "a.txt" in names
    assert "b.txt" not in names


def test_scan_recursive(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"y")
    names = {fi.path.name for fi in fsops.scan(tmp_path, recursive=True)}
    assert {"a.txt", "b.txt"} <= names


def test_file_hash_matches(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"content123")
    import hashlib

    assert fsops.file_hash(p) == hashlib.sha256(b"content123").hexdigest()


def test_move_symlink_preserves_link(tmp_path):
    target = tmp_path / "t.dat"
    target.write_bytes(b"data")
    link = tmp_path / "l.jpg"
    link.symlink_to(target)
    dst = tmp_path / "out" / "l.jpg"
    fsops.atomic_move(link, dst)
    assert dst.is_symlink()
    assert not link.exists()


def test_unicode_filename_move(tmp_path):
    src = tmp_path / "café.txt"
    src.write_bytes(b"u")
    dst = tmp_path / "out" / "café.txt"
    fsops.atomic_move(src, dst)
    assert dst.exists()
