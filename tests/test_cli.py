import json
from pathlib import Path

import pytest

from file_organizer.cli import cli


def _seed(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x" * 10)
    (tmp_path / "b.txt").write_bytes(b"y" * 5)
    (tmp_path / "c.pdf").write_bytes(b"z" * 7)


def test_preview_no_changes(runner, tmp_path):
    _seed(tmp_path)
    result = runner.invoke(cli, ["preview", str(tmp_path)])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    # nothing moved
    assert (tmp_path / "a.jpg").exists()


def test_organize_moves(runner, tmp_path):
    _seed(tmp_path)
    result = runner.invoke(
        cli, ["organize", str(tmp_path), "--undo-log", str(tmp_path / "u.jsonl")]
    )
    assert result.exit_code == 0
    # default config nests images by date under Images/{year}/{month}
    assert list((tmp_path / "Images").rglob("a.jpg"))
    assert (tmp_path / "Documents" / "b.txt").exists()


def test_report_json(runner, tmp_path):
    _seed(tmp_path)
    result = runner.invoke(cli, ["report", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert "by_rule" in data


def test_organize_json(runner, tmp_path):
    _seed(tmp_path)
    result = runner.invoke(
        cli,
        ["organize", str(tmp_path), "--json", "--undo-log", str(tmp_path / "u.jsonl")],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["moved"] >= 2


def test_undo_roundtrip(runner, tmp_path):
    _seed(tmp_path)
    ulog = str(tmp_path / "u.jsonl")
    r1 = runner.invoke(cli, ["organize", str(tmp_path), "--undo-log", ulog])
    assert r1.exit_code == 0
    assert not (tmp_path / "a.jpg").exists()
    r2 = runner.invoke(cli, ["undo", "--undo-log", ulog])
    assert r2.exit_code == 0
    assert (tmp_path / "a.jpg").exists()


def test_init_config(runner, tmp_path):
    out = tmp_path / "cfg.yaml"
    result = runner.invoke(cli, ["init-config", "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "rules:" in out.read_text()


def test_init_config_refuses_overwrite(runner, tmp_path):
    out = tmp_path / "cfg.yaml"
    out.write_text("existing")
    result = runner.invoke(cli, ["init-config", "-o", str(out)])
    assert result.exit_code != 0


def test_flag_override_conflict(runner, tmp_path):
    # documents rule sends txt to a flat {source}/Documents dir
    (tmp_path / "b.txt").write_bytes(b"new")
    dest = tmp_path / "Documents"
    dest.mkdir()
    (dest / "b.txt").write_bytes(b"old")
    result = runner.invoke(
        cli,
        [
            "organize",
            str(tmp_path),
            "--conflict",
            "skip",
            "--undo-log",
            str(tmp_path / "u.jsonl"),
        ],
    )
    assert result.exit_code == 0
    # skipped: original stays, destination untouched
    assert (tmp_path / "b.txt").exists()
    assert (dest / "b.txt").read_bytes() == b"old"


def test_error_path_bad_config(runner, tmp_path):
    _seed(tmp_path)
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules:\n  - name: x\n    match_regex: '([bad'\n    destination: d\n")
    result = runner.invoke(cli, ["organize", str(tmp_path), "-c", str(bad)])
    assert result.exit_code != 0
    assert "Error" in result.output


def test_config_flag_used(runner, tmp_path, fixtures_dir):
    _seed(tmp_path)
    result = runner.invoke(
        cli,
        [
            "organize",
            str(tmp_path),
            "-c",
            str(fixtures_dir / "sample-config.yaml"),
            "--undo-log",
            str(tmp_path / "u.jsonl"),
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "Documents" / "b.txt").exists()


def test_nonexistent_path(runner, tmp_path):
    result = runner.invoke(cli, ["organize", str(tmp_path / "nope")])
    assert result.exit_code != 0


def test_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output


def test_quiet_suppresses_output(runner, tmp_path):
    _seed(tmp_path)
    result = runner.invoke(
        cli,
        ["organize", str(tmp_path), "-q", "--undo-log", str(tmp_path / "u.jsonl")],
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""
