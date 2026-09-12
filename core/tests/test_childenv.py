"""No process the sidecar starts may inherit its secrets (SEC-27).

SEC-27 scrubbed ``MERIDIAN_*`` from observer probes and nowhere else. Git,
the sandboxed tool runner and the language-server bridge all inherited the
sidecar's full environment — ``MERIDIAN_LEDGER_SIGNING_KEY`` included — and
each runs code somebody else controls: repository hooks, configured build
tools, project-loaded LSP plugins. A negative control with a real pre-commit
hook read the key on the old path.

These pin the helper and, more importantly, refuse any future spawn that does
not pass an explicit environment. The failure mode being guarded against is
not a wrong value, it is an *absent* one — ``subprocess.run(cmd)`` with no
``env`` inherits everything and looks perfectly ordinary in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from meridian_core.childenv import SECRET_ENV_PREFIX, child_environment

PACKAGE = Path(__file__).resolve().parents[1] / "meridian_core"
SPAWNS = {"run", "Popen", "call", "check_call", "check_output"}


class TestTheHelper:
    def test_meridian_variables_never_cross(self, monkeypatch):
        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        monkeypatch.setenv("MERIDIAN_ANYTHING_ADDED_LATER", "x")
        assert not [key for key in child_environment() if key.startswith("MERIDIAN_")]

    def test_scrubbing_is_not_emptying(self, monkeypatch):
        # PATH and friends are how a child finds its own tools. Removing them
        # would break every spawn rather than secure it.
        monkeypatch.setenv("MERIDIAN_LEDGER_SIGNING_KEY", "s3cret")
        import os

        assert child_environment().get("PATH") == os.environ.get("PATH")

    def test_extra_values_are_added(self):
        assert child_environment({"GIT_PAGER": "cat"})["GIT_PAGER"] == "cat"

    def test_extra_cannot_smuggle_a_secret_back_in(self):
        # A caller that genuinely needs a Meridian setting inside a child has
        # to do it somewhere a reviewer will see, not through here.
        with pytest.raises(ValueError, match="SEC-27"):
            child_environment({"MERIDIAN_LEDGER_SIGNING_KEY": "s3cret"})

    def test_it_is_the_same_rule_the_observers_use(self):
        from meridian_core.observers import isolation

        assert SECRET_ENV_PREFIX == isolation.SECRET_ENV_PREFIX


def _spawns_without_env(root: Path | None = None) -> list[str]:
    """Walk `root` (the package by default).

    The root is a parameter so the negative control can plant its probe
    in a tmp dir instead of inside the package. Planting it in the
    package raced other guards that walk the same tree under `-n auto`:
    a worker saw the probe, then it was deleted before the read, and
    an unrelated guard died with FileNotFoundError. A test that makes
    another test flaky is not a test anyone can trust.
    """
    base = root or PACKAGE
    offenders: list[str] = []
    for path in base.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            spawn = (
                isinstance(func, ast.Attribute)
                and func.attr in SPAWNS
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            )
            shell_escape = (
                isinstance(func, ast.Attribute)
                and func.attr in {"system", "popen"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            )
            where = f"{path.relative_to(base)}:{node.lineno}"
            if shell_escape:
                # These cannot take an environment at all.
                offenders.append(f"{where} (os.{func.attr} cannot be scrubbed)")
            elif spawn and not any(keyword.arg == "env" for keyword in node.keywords):
                offenders.append(where)
    return sorted(offenders)


def test_every_spawn_passes_an_explicit_environment():
    """The guard that keeps the fix from eroding.

    An AST walk rather than a text search: the text scanners elsewhere in
    this suite had to be narrowed twice after matching prose in docstrings,
    and a multi-line call is invisible to a line-based check anyway.
    """
    offenders = _spawns_without_env()
    assert not offenders, (
        "these start a process that inherits the sidecar's whole environment, "
        "MERIDIAN_LEDGER_SIGNING_KEY included, and several of them run code "
        f"someone else controls: {', '.join(offenders)}. Pass "
        "env=meridian_core.childenv.child_environment()."
    )


def test_the_guard_actually_detects_an_unscrubbed_spawn(tmp_path):
    """A guard that cannot fail proves nothing — so make it fail once.

    Planted in a tmp dir rather than inside the package: the package is
    walked concurrently by other guards under `-n auto`, and a file that
    appears and vanishes there makes an unrelated test fail.
    """
    (tmp_path / "_planted_spawn_probe.py").write_text(
        "import subprocess\n\ndef leak():\n    subprocess.run(['git', 'status'])\n",
        encoding="utf-8",
    )
    assert any(
        "_planted_spawn_probe.py" in hit for hit in _spawns_without_env(tmp_path)
    )
