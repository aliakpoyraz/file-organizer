import threading
import time
from pathlib import Path

import pytest

from file_organizer.config import Config, Options, RuleSpec
from file_organizer.organizer import Organizer
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog
from file_organizer.watcher import Watcher, _stable_size

IMG_RULE = RuleSpec(
    name="images", destination="{source}/Images", extensions=["jpg"], priority=10
)


def build(rules, **opts):
    cfg = Config(options=Options(**opts), rules=rules)
    cfg.validate()
    return Organizer(cfg, RuleEngine(rules))


def _run_watcher_in_thread(watcher):
    t = threading.Thread(target=watcher.run, daemon=True)
    t.start()
    return t


def test_dropped_file_organized_after_settle(tmp_path):
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "u.jsonl")
    watcher = Watcher(org, tmp_path, settle_seconds=0.2, undo_log=log)
    t = _run_watcher_in_thread(watcher)
    time.sleep(0.3)  # let observer start
    (tmp_path / "photo.jpg").write_bytes(b"data")
    # wait for settle + processing
    deadline = time.time() + 5
    while time.time() < deadline:
        if (tmp_path / "Images" / "photo.jpg").exists():
            break
        time.sleep(0.1)
    watcher.stop_event.set()
    t.join(timeout=5)
    assert (tmp_path / "Images" / "photo.jpg").exists()
    assert watcher.aggregate.moved == 1


def test_half_written_not_moved_early(tmp_path):
    # A file whose size keeps changing should not be considered stable.
    p = tmp_path / "growing.jpg"
    p.write_bytes(b"x")

    import file_organizer.watcher as w

    sizes = iter([1, 2])  # two different reads -> unstable

    orig_stat = Path.stat

    # Simpler: directly test _stable_size with a file we grow between reads.
    def grow_during(path, wait=0.05):
        # emulate: first read 1, then grow, then read 2
        return _stable_size(path, wait=0.05)

    # Write differing content across the two internal reads by using a thread.
    def grower():
        time.sleep(0.02)
        p.write_bytes(b"xxxxxx")

    gt = threading.Thread(target=grower)
    gt.start()
    stable = _stable_size(p, wait=0.1)
    gt.join()
    assert stable is False
    # once settled it is stable
    assert _stable_size(p, wait=0.02) is True


def test_stop_event_clean_shutdown(tmp_path):
    org = build([IMG_RULE])
    watcher = Watcher(org, tmp_path, settle_seconds=0.2)
    t = _run_watcher_in_thread(watcher)
    time.sleep(0.3)
    watcher.stop_event.set()
    t.join(timeout=5)
    assert not t.is_alive()


def test_self_move_ignored(tmp_path):
    org = build([IMG_RULE])
    watcher = Watcher(org, tmp_path, settle_seconds=0.1)
    # register the Images dir as a known destination root
    watcher._dest_roots.add(str((tmp_path / "Images")))
    out = tmp_path / "Images"
    out.mkdir()
    f = out / "already.jpg"
    f.write_bytes(b"d")
    # processing a path inside a dest root should be ignored
    watcher.handler._note(str(f))
    watcher._process(str(f))
    # file remains where it is, not re-moved
    assert f.exists()
    assert watcher.aggregate.moved == 0


def test_handler_debounce_due(tmp_path):
    from file_organizer.watcher import OrganizeHandler

    h = OrganizeHandler(tmp_path)
    h._note(str(tmp_path / "x.jpg"))
    assert h.due(10.0) == []  # not settled yet
    time.sleep(0.05)
    assert str(tmp_path / "x.jpg") in h.due(0.0)
    h.clear(str(tmp_path / "x.jpg"))
    assert h.due(0.0) == []
