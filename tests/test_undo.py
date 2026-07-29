import json
from pathlib import Path

import pytest

from file_organizer.config import Config, Options, RuleSpec
from file_organizer.errors import UndoError
from file_organizer.models import ConflictStrategy
from file_organizer.organizer import Organizer
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog

IMG_RULE = RuleSpec(
    name="images", destination="{source}/Images", extensions=["jpg"], priority=10
)


def build(rules, **opts):
    cfg = Config(options=Options(**opts), rules=rules)
    cfg.validate()
    return Organizer(cfg, RuleEngine(rules))


def test_organize_then_undo_restores_tree(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"hello")
    (tmp_path / "b.jpg").write_bytes(b"world")
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    assert (tmp_path / "Images" / "a.jpg").exists()
    assert not (tmp_path / "a.jpg").exists()

    report = log.revert_last()
    assert report.moved == 2
    assert (tmp_path / "a.jpg").read_bytes() == b"hello"
    assert (tmp_path / "b.jpg").read_bytes() == b"world"
    assert not (tmp_path / "Images" / "a.jpg").exists()


def test_undo_removes_empty_created_dirs(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"hello")
    rule = RuleSpec(
        name="images", destination="{source}/Images/{year}", extensions=["jpg"],
        date_bucket=True, priority=10,
    )
    org = build([rule])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    images = tmp_path / "Images"
    assert images.is_dir()

    log.revert_last()
    assert (tmp_path / "a.jpg").exists()
    # nested folders created by organize are gone, source itself stays
    assert not images.exists()
    assert tmp_path.is_dir()


def test_undo_keeps_dir_with_other_files(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"hello")
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    # user drops an unrelated file into the created folder
    (tmp_path / "Images" / "keep.me").write_text("x", encoding="utf-8")

    log.revert_last()
    assert (tmp_path / "a.jpg").exists()
    assert (tmp_path / "Images").is_dir()  # not empty -> kept
    assert (tmp_path / "Images" / "keep.me").exists()


def test_undo_dry_run_no_changes(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    report = log.revert_last(dry_run=True)
    assert report.dry_run is True
    assert report.moved == 1
    # still moved, not reverted
    assert (tmp_path / "Images" / "a.jpg").exists()
    assert not (tmp_path / "a.jpg").exists()


def test_overwrite_backup_restored(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"new")
    dest = tmp_path / "Images"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"old")
    org = build([IMG_RULE], conflict_strategy=ConflictStrategy.OVERWRITE)
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    assert (dest / "a.jpg").read_bytes() == b"new"

    log.revert_last()
    # original source restored
    assert (tmp_path / "a.jpg").read_bytes() == b"new"
    # backup restored to destination slot
    assert (dest / "a.jpg").read_bytes() == b"old"


def test_double_undo_no_re_revert(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    log.revert_last()
    with pytest.raises(UndoError):
        log.revert_last()


def test_interrupted_op_revertible(tmp_path):
    # Simulate an op with no op_end (crash mid-run).
    log_path = tmp_path / "undo.jsonl"
    (tmp_path / "a.jpg").write_bytes(b"data")
    dest = tmp_path / "Images"
    dest.mkdir()
    # actually move the file so undo has something to restore
    import shutil

    shutil.move(str(tmp_path / "a.jpg"), str(dest / "a.jpg"))
    records = [
        {"type": "op_start", "op": "op1", "dry_run": False, "root": str(tmp_path)},
        {
            "type": "move",
            "op": "op1",
            "source": str(tmp_path / "a.jpg"),
            "destination": str(dest / "a.jpg"),
            "rule": "images",
            "strategy": "rename",
            "backup": None,
            "ts": "t",
        },
        # no op_end
    ]
    with log_path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    log = UndoLog(log_path)
    report = log.revert_last()
    assert report.moved == 1
    assert (tmp_path / "a.jpg").read_bytes() == b"data"


def test_undo_empty_log_raises(tmp_path):
    log = UndoLog(tmp_path / "undo.jsonl")
    with pytest.raises(UndoError):
        log.revert_last()


def test_undo_skips_missing_destination(tmp_path):
    log_path = tmp_path / "undo.jsonl"
    records = [
        {"type": "op_start", "op": "op1", "dry_run": False},
        {
            "type": "move",
            "op": "op1",
            "source": str(tmp_path / "gone.jpg"),
            "destination": str(tmp_path / "nowhere.jpg"),
            "rule": "images",
            "strategy": "rename",
            "backup": None,
        },
    ]
    with log_path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    log = UndoLog(log_path)
    report = log.revert_last()
    assert report.skipped == 1
    assert report.errors


def test_dry_run_op_not_reverted(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    org = build([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    # a real run
    org.execute(org.plan(tmp_path), undo_log=log)
    # append a dry-run op_start manually (should be ignored by revert)
    log.append({"type": "op_start", "op": "dry1", "dry_run": True})
    report = log.revert_last()
    # the real op is reverted, not the dry one
    assert report.moved == 1
    assert (tmp_path / "a.jpg").exists()
