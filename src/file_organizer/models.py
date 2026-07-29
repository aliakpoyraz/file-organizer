"""Pure data models. No I/O happens in this module."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SizeBucket(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ConflictStrategy(str, Enum):
    RENAME = "rename"
    SKIP = "skip"
    OVERWRITE = "overwrite"


class DateBasis(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"


class ActionStatus(str, Enum):
    PLANNED = "planned"
    MOVED = "moved"
    SKIPPED = "skipped"
    FAILED = "failed"
    OVERWRITTEN = "overwritten"


@dataclass(frozen=True)
class FileInfo:
    """Immutable snapshot of a file's stat information."""

    path: Path
    size: int
    created: float
    modified: float
    is_symlink: bool
    ext: str  # lowercased, no leading dot


@dataclass
class PlannedAction:
    source: Path
    destination: Path
    rule_name: str
    status: ActionStatus
    reason: str = ""


@dataclass
class MoveRecord:
    source: str
    destination: str
    rule: str
    strategy: str
    overwritten_backup: str | None
    ts: str
