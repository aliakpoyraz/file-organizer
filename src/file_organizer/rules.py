"""Rule matching engine."""

from __future__ import annotations

import fnmatch
import re

from file_organizer.config import RuleSpec
from file_organizer.models import FileInfo, SizeBucket

SMALL_MAX_DEFAULT = 1024**2  # 1 MB
LARGE_MIN_DEFAULT = 100 * 1024**2  # 100 MB


def size_bucket(
    size: int,
    small_max: int = SMALL_MAX_DEFAULT,
    large_min: int = LARGE_MIN_DEFAULT,
) -> SizeBucket:
    if size <= small_max:
        return SizeBucket.SMALL
    if size >= large_min:
        return SizeBucket.LARGE
    return SizeBucket.MEDIUM


class RuleEngine:
    """Compile, order and evaluate a list of :class:`RuleSpec` rules."""

    def __init__(self, rules: list[RuleSpec]):
        self.rules = list(rules)
        for rule in self.rules:
            if rule.match_regex is not None and rule._regex is None:
                rule._regex = re.compile(rule.match_regex)
        # Stable sort: priority desc, then specificity desc, keep config order.
        self._ordered = sorted(
            enumerate(self.rules),
            key=lambda pair: (-pair[1].priority, -pair[1].selector_count, pair[0]),
        )
        self.ordered = [rule for _, rule in self._ordered]

    def match(self, fi: FileInfo) -> RuleSpec | None:
        """Return the first rule whose active selectors all match, else None."""
        for rule in self.ordered:
            if self._matches(rule, fi):
                return rule
        return None

    @staticmethod
    def _matches(rule: RuleSpec, fi: FileInfo) -> bool:
        if rule.is_catch_all:
            return True

        if rule.extensions is not None:
            if fi.ext not in rule.extensions:
                return False

        if rule.size_range is not None:
            lo, hi = rule.size_range
            if lo is not None and fi.size < lo:
                return False
            if hi is not None and fi.size > hi:
                return False

        if rule.min_size is not None:
            if fi.size < rule.min_size:
                return False

        if rule.match_regex is not None:
            if not rule._regex.search(fi.path.name):
                return False

        if rule.match_glob is not None:
            if not fnmatch.fnmatch(fi.path.name, rule.match_glob):
                return False

        return True
