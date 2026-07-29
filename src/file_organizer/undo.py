"""Append-only JSON Lines undo log and revert logic."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

from file_organizer.errors import UndoError
from file_organizer.fsops import atomic_move
from file_organizer.report import RunReport


def new_op_id() -> str:
    return f"{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}"


class UndoLog:
    """Read/write the append-only undo log."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _read_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def read_operations(self) -> dict[str, list[dict]]:
        """Group all records by their ``op`` id, preserving insertion order."""
        ops: dict[str, list[dict]] = {}
        for rec in self._read_records():
            op = rec.get("op")
            if op is None:
                continue
            ops.setdefault(op, []).append(rec)
        return ops

    def _undone_ops(self, records: list[dict]) -> set[str]:
        undone = set()
        for rec in records:
            if rec.get("type") == "op_undo":
                target = rec.get("target")
                if target:
                    undone.add(target)
        return undone

    def revert_last(self, dry_run: bool = False) -> RunReport:
        """Revert the most recent real (non-dry-run, not-yet-undone) operation."""
        records = self._read_records()
        if not records:
            raise UndoError("Undo log is empty; nothing to revert")

        undone = self._undone_ops(records)

        # Find the last op_start that is a real op and not yet undone.
        starts = [
            rec
            for rec in records
            if rec.get("type") == "op_start"
            and not rec.get("dry_run", False)
            and rec.get("op") not in undone
        ]
        if not starts:
            raise UndoError("No revertible operation found")
        target_op = starts[-1]["op"]

        moves = [
            rec
            for rec in records
            if rec.get("op") == target_op and rec.get("type") == "move"
        ]

        report = RunReport(dry_run=dry_run)
        # Replay in reverse order.
        for rec in reversed(moves):
            self._revert_one(rec, report, dry_run)

        if not dry_run:
            # Remove destination folders left empty after moving files back.
            dest_dirs = {Path(rec["destination"]).parent for rec in moves}
            self._prune_empty_dirs(dest_dirs)
            self.append(
                {
                    "type": "op_undo",
                    "op": new_op_id(),
                    "target": target_op,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        return report

    def _prune_empty_dirs(self, dirs: set[Path]) -> None:
        """Remove now-empty directories created during the organize run.

        Walks upward from each destination folder, deleting empty ones until a
        non-empty directory (e.g. the original source folder) stops the chain.
        Only empty directories are ever removed.
        """
        for start in dirs:
            current = start
            while True:
                parent = current.parent
                if parent == current:  # reached filesystem root
                    break
                try:
                    if not current.is_dir() or any(current.iterdir()):
                        break
                    current.rmdir()
                except OSError:
                    break
                current = parent

    def _revert_one(self, rec: dict, report: RunReport, dry_run: bool) -> None:
        source = Path(rec["source"])
        destination = Path(rec["destination"])
        backup = rec.get("backup")

        if not destination.exists():
            report.skipped += 1
            report.errors.append(
                (str(destination), "missing at undo time; skipped")
            )
            return
        if source.exists():
            report.skipped += 1
            report.errors.append(
                (str(source), "original location occupied; skipped")
            )
            return

        if dry_run:
            report.moved += 1
            report.by_rule[rec.get("rule", "?")] += 1
            return

        try:
            atomic_move(destination, source, verify_hash=True)
        except Exception as exc:  # noqa: BLE001 - record and continue
            report.failed += 1
            report.errors.append((str(destination), f"undo failed: {exc}"))
            return

        report.moved += 1
        report.by_rule[rec.get("rule", "?")] += 1

        # Restore any overwritten backup back into the destination slot.
        if backup:
            backup_path = Path(backup)
            if backup_path.exists():
                try:
                    atomic_move(backup_path, destination, verify_hash=True)
                    report.overwritten += 1
                except Exception as exc:  # noqa: BLE001
                    report.errors.append(
                        (str(backup_path), f"backup restore failed: {exc}")
                    )
