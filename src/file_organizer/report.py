"""Run reporting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class RunReport:
    moved: int = 0
    skipped: int = 0
    failed: int = 0
    overwritten: int = 0
    dry_run: bool = False
    by_rule: Counter = field(default_factory=Counter)
    bytes_moved: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "moved": self.moved,
            "skipped": self.skipped,
            "failed": self.failed,
            "overwritten": self.overwritten,
            "dry_run": self.dry_run,
            "by_rule": dict(self.by_rule),
            "bytes_moved": self.bytes_moved,
            "errors": [list(e) for e in self.errors],
        }

    def render(self, verbose: bool = False) -> str:
        prefix = "DRY-RUN " if self.dry_run else ""
        lines = [
            f"{prefix}Summary:",
            f"  moved:       {self.moved}",
            f"  skipped:     {self.skipped}",
            f"  overwritten: {self.overwritten}",
            f"  failed:      {self.failed}",
            f"  bytes moved: {self.bytes_moved}",
        ]
        if self.by_rule:
            lines.append("  by rule:")
            for rule, count in sorted(self.by_rule.items()):
                lines.append(f"    {rule}: {count}")
        if verbose and self.errors:
            lines.append("  errors:")
            for src, msg in self.errors:
                lines.append(f"    {src}: {msg}")
        return "\n".join(lines)
