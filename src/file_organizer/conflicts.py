"""Conflict-resolution strategies for a destination path."""

from __future__ import annotations

import time
from pathlib import Path

from file_organizer.fsops import unique_path
from file_organizer.models import ConflictStrategy


def resolve_conflict(
    dst: str | Path, strategy: ConflictStrategy
) -> tuple[Path | None, Path | None]:
    """Return ``(final_dest, backup_path)``.

    ``final_dest`` is ``None`` when the file should be skipped.
    ``backup_path`` is set only when an existing file must be preserved
    (OVERWRITE strategy) so undo can restore it later.
    """
    dst = Path(dst)
    if not dst.exists():
        return dst, None

    if strategy == ConflictStrategy.RENAME:
        return unique_path(dst), None

    if strategy == ConflictStrategy.SKIP:
        return None, None

    if strategy == ConflictStrategy.OVERWRITE:
        ts = time.strftime("%Y%m%d%H%M%S")
        backup = dst.with_name(f"{dst.name}.bak-{ts}")
        # Ensure the backup name is itself unique.
        backup = unique_path(backup)
        return dst, backup

    raise ValueError(f"Unknown conflict strategy: {strategy!r}")
