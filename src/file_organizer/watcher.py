"""Watch-mode filesystem monitoring with graceful shutdown."""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from file_organizer.organizer import Organizer
from file_organizer.report import RunReport
from file_organizer.undo import UndoLog


class OrganizeHandler(FileSystemEventHandler):
    """Collect created / moved-into events and debounce them."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def _note(self, path: str) -> None:
        with self._lock:
            self._pending[path] = time.monotonic()

    def on_created(self, event):
        if event.is_directory:
            return
        self._note(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None)
        if dest:
            self._note(dest)

    def due(self, settle_seconds: float) -> list[str]:
        """Return paths that have settled (no events for settle_seconds)."""
        now = time.monotonic()
        ready = []
        with self._lock:
            for path, last in list(self._pending.items()):
                if now - last >= settle_seconds:
                    ready.append(path)
        return ready

    def clear(self, path: str) -> None:
        with self._lock:
            self._pending.pop(path, None)


def _stable_size(path: Path, wait: float = 0.05) -> bool:
    """Return True if the file's size is stable across two reads."""
    try:
        first = path.stat().st_size
    except OSError:
        return False
    time.sleep(wait)
    try:
        second = path.stat().st_size
    except OSError:
        return False
    return first == second


class Watcher:
    def __init__(
        self,
        organizer: Organizer,
        root: str | Path,
        *,
        settle_seconds: float = 2.0,
        undo_log: UndoLog | None = None,
        report_cb: Callable[[RunReport], None] | None = None,
    ):
        self.organizer = organizer
        self.root = Path(root).absolute()
        self.settle_seconds = settle_seconds
        self.undo_log = undo_log
        self.report_cb = report_cb
        self.stop_event = threading.Event()
        self.handler = OrganizeHandler(self.root)
        self.observer = Observer()
        self.aggregate = RunReport()
        self._force_count = 0
        self._dest_roots: set[str] = set()

    def _is_own_output(self, path: Path) -> bool:
        """Ignore files that resolve inside a known destination root."""
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        return any(resolved.startswith(root) for root in self._dest_roots)

    def _process(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.exists():
            self.handler.clear(path_str)
            return
        if self._is_own_output(path):
            self.handler.clear(path_str)
            return
        if not _stable_size(path):
            # Still being written; leave it pending and re-note it.
            self.handler._note(path_str)
            return

        # Build a single-file plan by planning the whole root and filtering.
        actions = [
            a
            for a in self.organizer.plan(self.root)
            if str(a.source) == str(path)
        ]
        self.handler.clear(path_str)
        if not actions:
            return
        for action in actions:
            if action.destination and action.rule_name:
                self._dest_roots.add(str(action.destination.parent))
        report = self.organizer.execute(
            actions,
            dry_run=self.organizer.options.dry_run,
            undo_log=self.undo_log,
        )
        self._merge(report)

    def _merge(self, report: RunReport) -> None:
        self.aggregate.moved += report.moved
        self.aggregate.skipped += report.skipped
        self.aggregate.failed += report.failed
        self.aggregate.overwritten += report.overwritten
        self.aggregate.bytes_moved += report.bytes_moved
        self.aggregate.by_rule.update(report.by_rule)
        self.aggregate.errors.extend(report.errors)

    def install_signal_handlers(self) -> None:
        def handler(signum, frame):  # noqa: ARG001
            self._force_count += 1
            if self._force_count >= 2:
                os._exit(1)
            self.stop_event.set()

        signal.signal(signal.SIGINT, handler)
        try:
            signal.signal(signal.SIGTERM, handler)
        except (ValueError, OSError):
            pass

    def run(self) -> RunReport:
        self.observer.schedule(self.handler, str(self.root), recursive=False)
        self.observer.start()
        try:
            while not self.stop_event.wait(0.5):
                for path_str in self.handler.due(self.settle_seconds):
                    self._process(path_str)
        finally:
            # Finish any in-flight settled files before shutting down.
            for path_str in self.handler.due(0):
                try:
                    self._process(path_str)
                except Exception:  # noqa: BLE001
                    pass
            self.observer.stop()
            self.observer.join(timeout=5)
        return self.aggregate
