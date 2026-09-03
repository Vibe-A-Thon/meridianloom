"""Shared pytest fixtures for sidecar tests.

The fixture git repo lives next to its builder (test_attribution.py) and is
re-exported here so other test modules (test_symbols, test_heuristics) can
count on a small committed repository without rebuilding it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_attribution import ALICE, T0, git


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path
