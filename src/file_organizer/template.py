"""Destination-directory template resolution."""

from __future__ import annotations

import calendar
from datetime import datetime
from pathlib import Path
from string import Formatter

from file_organizer.errors import RuleError
from file_organizer.models import DateBasis, FileInfo, SizeBucket

_KNOWN_PLACEHOLDERS = {
    "source",
    "ext",
    "year",
    "month",
    "month_name",
    "day",
    "size_bucket",
    "name",
    "rule",
}


def _size_bucket_for(size: int, small_max: int, large_min: int) -> SizeBucket:
    if size <= small_max:
        return SizeBucket.SMALL
    if size >= large_min:
        return SizeBucket.LARGE
    return SizeBucket.MEDIUM


def resolve(
    template: str,
    fi: FileInfo,
    root: Path,
    basis: DateBasis,
    *,
    rule_name: str = "",
    small_max: int = 1024**2,
    large_min: int = 100 * 1024**2,
) -> Path:
    """Resolve ``template`` into an absolute destination *directory* Path.

    The filename itself is appended later by the organizer.
    """
    ts = fi.created if basis == DateBasis.CREATED else fi.modified
    dt = datetime.fromtimestamp(ts)
    bucket = _size_bucket_for(fi.size, small_max, large_min)
    values = {
        "source": str(root),
        "ext": fi.ext,
        "year": f"{dt.year:04d}",
        "month": f"{dt.month:02d}",
        "month_name": calendar.month_name[dt.month],
        "day": f"{dt.day:02d}",
        "size_bucket": bucket.value,
        "name": fi.path.stem,
        "rule": rule_name,
    }

    # Validate placeholders up front for a clear error.
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name is None:
            continue
        key = field_name.split(".")[0].split("[")[0]
        if key and key not in _KNOWN_PLACEHOLDERS:
            raise RuleError(
                f"Unknown placeholder {{{field_name}}} in template {template!r}"
            )

    try:
        rendered = template.format(**values)
    except (KeyError, IndexError, ValueError) as exc:
        raise RuleError(
            f"Cannot render template {template!r}: {exc}"
        ) from exc

    return Path(rendered).expanduser().absolute()
