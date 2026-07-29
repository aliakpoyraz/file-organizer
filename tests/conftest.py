"""Shared pytest fixtures."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from file_organizer.config import Config, load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_tree(tmp_path):
    """Factory that populates ``tmp_path`` with files.

    Usage: ``root = tmp_tree([("a.jpg", 1000), ("b.txt", 20)])``.
    Each spec is ``(name, size)`` or ``(name, size, mtime)``.
    Also creates one unicode-named file and one symlink by default.
    """

    def _make(specs=None, *, subdir=None, unicode_file=True, symlink=True):
        root = tmp_path if subdir is None else tmp_path / subdir
        root.mkdir(parents=True, exist_ok=True)
        created = []
        specs = specs or []
        for spec in specs:
            if len(spec) == 2:
                name, size = spec
                mtime = None
            else:
                name, size, mtime = spec
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x" * size)
            if mtime is not None:
                os.utime(p, (mtime, mtime))
            created.append(p)
        if unicode_file:
            up = root / "résumé-café.txt"
            up.write_bytes(b"unicode content")
            created.append(up)
        if symlink:
            target = root / "link-target.dat"
            target.write_bytes(b"target")
            link = root / "a-link.jpg"
            try:
                link.symlink_to(target)
                created.append(link)
            except (OSError, NotImplementedError):
                pass
        return root

    return _make


@pytest.fixture
def sample_config():
    return load_config(FIXTURES / "sample-config.yaml")


@pytest.fixture
def default_config():
    return Config.default()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fixtures_dir():
    return FIXTURES
