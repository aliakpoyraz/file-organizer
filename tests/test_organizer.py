from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.config import Config, Options, RuleSpec
from file_organizer.models import ActionStatus, ConflictStrategy
from file_organizer.organizer import Organizer
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog


def build_organizer(rules, **opts):
    options = Options(**opts)
    cfg = Config(options=options, rules=rules)
    cfg.validate()
    return Organizer(cfg, RuleEngine(rules))


IMG_RULE = RuleSpec(
    name="images", destination="{source}/Images", extensions=["jpg", "png"], priority=10
)
DOC_RULE = RuleSpec(
    name="docs", destination="{source}/Documents", extensions=["txt"], priority=10
)
CATCH = RuleSpec(name="other", destination="{source}/Other", priority=0)


def test_dry_run_no_fs_changes(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x" * 10)
    (tmp_path / "b.txt").write_bytes(b"y" * 5)
    org = build_organizer([IMG_RULE, DOC_RULE], dry_run=True)
    report = org.run(tmp_path, progress=False)
    assert report.dry_run is True
    assert report.moved == 2
    # nothing actually moved
    assert (tmp_path / "a.jpg").exists()
    assert not (tmp_path / "Images").exists()


def test_real_run_moves_and_classifies(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x" * 10)
    (tmp_path / "b.txt").write_bytes(b"y" * 5)
    (tmp_path / "c.xyz").write_bytes(b"z" * 3)
    org = build_organizer([IMG_RULE, DOC_RULE, CATCH])
    log = UndoLog(tmp_path / "undo.jsonl")
    report = org.execute(org.plan(tmp_path), undo_log=log)
    assert report.moved == 3
    assert (tmp_path / "Images" / "a.jpg").exists()
    assert (tmp_path / "Documents" / "b.txt").exists()
    assert (tmp_path / "Other" / "c.xyz").exists()
    assert report.by_rule["images"] == 1
    assert report.by_rule["docs"] == 1
    assert report.bytes_moved == 18


def test_skipped_no_rule(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.xyz").write_bytes(b"y")
    org = build_organizer([IMG_RULE])  # no catch-all
    actions = org.plan(tmp_path)
    report = org.execute(actions)
    assert report.moved == 1
    assert report.skipped == 1


def test_recursive(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.jpg").write_bytes(b"y")
    org = build_organizer([IMG_RULE], recursive=True)
    report = org.execute(org.plan(tmp_path))
    assert report.moved == 2


def test_symlink_skipped_by_default(tmp_path):
    target = tmp_path / "t.dat"
    target.write_bytes(b"d")
    link = tmp_path / "l.jpg"
    link.symlink_to(target)
    (tmp_path / "real.jpg").write_bytes(b"r")
    org = build_organizer([IMG_RULE, CATCH])
    actions = org.plan(tmp_path)
    statuses = {a.source.name: a for a in actions}
    assert statuses["l.jpg"].status == ActionStatus.SKIPPED
    assert "symlink" in statuses["l.jpg"].reason


def test_conflict_rename(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"1")
    dest = tmp_path / "Images"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"existing")
    org = build_organizer([IMG_RULE], conflict_strategy=ConflictStrategy.RENAME)
    report = org.execute(org.plan(tmp_path))
    assert report.moved == 1
    assert (dest / "a.jpg").read_bytes() == b"existing"
    assert (dest / "a (1).jpg").exists()


def test_conflict_skip(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"1")
    dest = tmp_path / "Images"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"existing")
    org = build_organizer([IMG_RULE], conflict_strategy=ConflictStrategy.SKIP)
    report = org.execute(org.plan(tmp_path))
    assert report.skipped == 1
    assert (tmp_path / "a.jpg").exists()


def test_conflict_overwrite(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"new")
    dest = tmp_path / "Images"
    dest.mkdir()
    (dest / "a.jpg").write_bytes(b"old")
    org = build_organizer(
        [IMG_RULE], conflict_strategy=ConflictStrategy.OVERWRITE
    )
    report = org.execute(org.plan(tmp_path))
    assert report.overwritten == 1
    assert (dest / "a.jpg").read_bytes() == b"new"
    backups = list(dest.glob("a.jpg.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old"


def test_dest_equals_source_skipped(tmp_path):
    # rule sends file to same dir it's already in
    rule = RuleSpec(name="here", destination="{source}", extensions=["jpg"])
    (tmp_path / "a.jpg").write_bytes(b"x")
    org = build_organizer([rule])
    actions = org.plan(tmp_path)
    a = actions[0]
    assert a.status == ActionStatus.SKIPPED
    assert "already at destination" in a.reason


def test_undo_log_written(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    org = build_organizer([IMG_RULE])
    log = UndoLog(tmp_path / "undo.jsonl")
    org.execute(org.plan(tmp_path), undo_log=log)
    ops = log.read_operations()
    assert len(ops) == 1
    types = [r["type"] for op in ops.values() for r in op]
    assert "op_start" in types
    assert "move" in types
    assert "op_end" in types
