"""Filesystem operations. This is the only module doing destructive I/O."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from file_organizer.errors import MoveError, PermissionDeniedError
from file_organizer.models import FileInfo


def stat_file(path: str | Path, follow_symlinks: bool = False) -> FileInfo:
    path = Path(path)
    st = path.stat() if follow_symlinks else path.stat(follow_symlinks=False)
    is_symlink = path.is_symlink()
    # st_birthtime where available (macOS), otherwise fall back to ctime.
    created = getattr(st, "st_birthtime", None)
    if created is None:
        created = st.st_ctime
    ext = path.suffix.lower().lstrip(".")
    return FileInfo(
        path=path,
        size=st.st_size,
        created=created,
        modified=st.st_mtime,
        is_symlink=is_symlink,
        ext=ext,
    )


def scan(
    root: str | Path,
    recursive: bool = False,
    follow_symlinks: bool = False,
) -> Iterator[FileInfo]:
    """Yield :class:`FileInfo` for each file directly (or recursively) in root."""
    root = Path(root)
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
            for name in sorted(filenames):
                p = Path(dirpath) / name
                yield stat_file(p, follow_symlinks=follow_symlinks)
    else:
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if entry.is_symlink() and not follow_symlinks:
                yield stat_file(entry, follow_symlinks=False)
                continue
            if entry.is_dir():
                continue
            yield stat_file(entry, follow_symlinks=follow_symlinks)


def file_hash(path: str | Path, algo: str = "sha256", chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def ensure_dest_writable(dest_dir: str | Path) -> None:
    """Ensure ``dest_dir`` exists (create it) and is writable."""
    dest_dir = Path(dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionDeniedError(
            f"Cannot create destination directory {dest_dir}: {exc}"
        ) from exc
    if not os.access(dest_dir, os.W_OK):
        raise PermissionDeniedError(f"Destination not writable: {dest_dir}")


def unique_path(dst: str | Path) -> Path:
    """Return a non-colliding path by appending ``(1)``, ``(2)``, ... to the stem."""
    dst = Path(dst)
    if not dst.exists():
        return dst
    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def atomic_move(src: str | Path, dst: str | Path, verify_hash: bool = True) -> None:
    """Move ``src`` to ``dst`` atomically, leaving the original intact on failure.

    The strategy is copy -> fsync -> optional verify -> os.replace -> unlink(src).
    Works across devices because it never relies on ``os.rename`` across mounts.
    """
    src = Path(src)
    dst = Path(dst)
    dest_dir = dst.parent
    ensure_dest_writable(dest_dir)
    tmp = dest_dir / (dst.name + ".part")
    # Clean up any leftover .part from a prior interrupted run.
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    try:
        if src.is_symlink():
            # Preserve the link itself rather than its target.
            link_target = os.readlink(src)
            os.symlink(link_target, tmp)
        else:
            shutil.copy2(src, tmp)
            _fsync(tmp)
            if verify_hash:
                if file_hash(tmp) != file_hash(src):
                    raise MoveError(
                        f"Hash mismatch after copying {src} -> {dst}"
                    )
    except MoveError:
        _safe_unlink(tmp)
        raise
    except OSError as exc:
        _safe_unlink(tmp)
        raise MoveError(f"Failed to copy {src} -> {dst}: {exc}") from exc

    try:
        os.replace(tmp, dst)
    except OSError as exc:
        _safe_unlink(tmp)
        raise MoveError(f"Failed to finalize move {src} -> {dst}: {exc}") from exc

    try:
        src.unlink()
    except OSError as exc:
        raise MoveError(
            f"Moved data to {dst} but could not remove source {src}: {exc}"
        ) from exc


def _fsync(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # fsync is best-effort; not all filesystems support it.
        pass


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
