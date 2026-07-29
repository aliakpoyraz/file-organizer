"""Planning and execution of file organization."""

from __future__ import annotations

import time
import unicodedata
from pathlib import Path
from typing import Callable

from file_organizer import fsops, template
from file_organizer.conflicts import resolve_conflict
from file_organizer.config import Config
from file_organizer.errors import MoveError, OrganizerError
from file_organizer.models import ActionStatus, ConflictStrategy, PlannedAction
from file_organizer.report import RunReport
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog, new_op_id

ProgressCb = Callable[[PlannedAction], None]


class Organizer:
    def __init__(self, config: Config, engine: RuleEngine | None = None):
        self.config = config
        self.options = config.options
        self.engine = engine or RuleEngine(config.rules)

    # -- planning -----------------------------------------------------------
    def plan(self, root: str | Path) -> list[PlannedAction]:
        """Compute the list of planned actions with no side effects."""
        root = Path(root).absolute()
        actions: list[PlannedAction] = []
        for fi in fsops.scan(
            root,
            recursive=self.options.recursive,
            follow_symlinks=self.options.follow_symlinks,
        ):
            if fi.is_symlink and not self.options.follow_symlinks:
                actions.append(
                    PlannedAction(
                        source=fi.path,
                        destination=fi.path,
                        rule_name="",
                        status=ActionStatus.SKIPPED,
                        reason="symlink (follow_symlinks disabled)",
                    )
                )
                continue

            rule = self.engine.match(fi)
            if rule is None:
                actions.append(
                    PlannedAction(
                        source=fi.path,
                        destination=fi.path,
                        rule_name="",
                        status=ActionStatus.SKIPPED,
                        reason="no matching rule",
                    )
                )
                continue

            dest_dir = template.resolve(
                rule.destination,
                fi,
                root,
                self.options.date_basis,
                rule_name=rule.name,
            )
            filename = unicodedata.normalize("NFC", fi.path.name)
            dst = dest_dir / filename

            if dst == fi.path:
                actions.append(
                    PlannedAction(
                        source=fi.path,
                        destination=dst,
                        rule_name=rule.name,
                        status=ActionStatus.SKIPPED,
                        reason="already at destination",
                    )
                )
                continue

            final_dst, backup = resolve_conflict(
                dst, self.options.conflict_strategy
            )
            if final_dst is None:
                actions.append(
                    PlannedAction(
                        source=fi.path,
                        destination=dst,
                        rule_name=rule.name,
                        status=ActionStatus.SKIPPED,
                        reason="conflict: skip strategy",
                    )
                )
                continue

            status = (
                ActionStatus.OVERWRITTEN if backup is not None else ActionStatus.PLANNED
            )
            action = PlannedAction(
                source=fi.path,
                destination=final_dst,
                rule_name=rule.name,
                status=status,
            )
            action._backup = backup  # type: ignore[attr-defined]
            actions.append(action)
        return actions

    # -- execution ----------------------------------------------------------
    def execute(
        self,
        plan: list[PlannedAction],
        *,
        dry_run: bool = False,
        progress_cb: ProgressCb | None = None,
        undo_log: UndoLog | None = None,
    ) -> RunReport:
        report = RunReport(dry_run=dry_run)
        op_id = new_op_id()

        if undo_log is not None and not dry_run:
            undo_log.append(
                {
                    "type": "op_start",
                    "op": op_id,
                    "root": "",
                    "dry_run": dry_run,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )

        for action in plan:
            if progress_cb is not None:
                progress_cb(action)

            if action.status == ActionStatus.SKIPPED:
                report.skipped += 1
                continue

            backup = getattr(action, "_backup", None)

            if dry_run:
                # Classify only; no filesystem changes.
                if action.status == ActionStatus.OVERWRITTEN:
                    report.overwritten += 1
                else:
                    report.moved += 1
                report.by_rule[action.rule_name] += 1
                try:
                    report.bytes_moved += action.source.stat().st_size
                except OSError:
                    pass
                continue

            try:
                self._perform(action, backup, report, undo_log, op_id)
            except OrganizerError as exc:
                report.failed += 1
                report.errors.append((str(action.source), str(exc)))
                action.status = ActionStatus.FAILED
                action.reason = str(exc)

        if undo_log is not None and not dry_run:
            undo_log.append(
                {
                    "type": "op_end",
                    "op": op_id,
                    "moved": report.moved,
                    "failed": report.failed,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        return report

    def _perform(self, action, backup, report, undo_log, op_id):
        fsops.ensure_dest_writable(action.destination.parent)
        try:
            size = action.source.stat().st_size
        except OSError:
            size = 0

        # If overwriting, move the existing file to its backup first.
        if backup is not None and action.destination.exists():
            fsops.atomic_move(
                action.destination, backup, verify_hash=self.options.verify_hash
            )

        fsops.atomic_move(
            action.source,
            action.destination,
            verify_hash=self.options.verify_hash,
        )

        if backup is not None:
            report.overwritten += 1
            action.status = ActionStatus.OVERWRITTEN
        else:
            report.moved += 1
            action.status = ActionStatus.MOVED
        report.by_rule[action.rule_name] += 1
        report.bytes_moved += size

        if undo_log is not None:
            undo_log.append(
                {
                    "type": "move",
                    "op": op_id,
                    "source": str(action.source),
                    "destination": str(action.destination),
                    "rule": action.rule_name,
                    "strategy": self.options.conflict_strategy.value,
                    "backup": str(backup) if backup is not None else None,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )

    # -- convenience --------------------------------------------------------
    def run(
        self,
        root: str | Path,
        *,
        progress: bool = True,
        progress_cb: ProgressCb | None = None,
        undo_log: UndoLog | None = None,
    ) -> RunReport:
        actions = self.plan(root)
        if undo_log is None and not self.options.dry_run:
            undo_log = UndoLog(self.options.undo_log)
        return self.execute(
            actions,
            dry_run=self.options.dry_run,
            progress_cb=progress_cb,
            undo_log=undo_log,
        )
