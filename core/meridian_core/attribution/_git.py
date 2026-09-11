"""Shared git plumbing for the attribution engine.

Everything runs through the ``git`` binary on PATH (Windows included) with
quoting and colour disabled so output is parseable and deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..gitcmd import GitTimeout, run_git_command


class AttributionError(Exception):
    """A clean, user-actionable attribution failure (never a crash)."""


def run_git(repo: Path, *args: str) -> str:
    """Run one git command in ``repo`` and return stdout.

    Raises AttributionError with git's own stderr on failure so RPC handlers
    can surface a readable message instead of an internal error.
    """
    try:
        result = run_git_command(repo, *args)
    except FileNotFoundError as error:
        raise AttributionError(
            "git executable not found on PATH; attribution requires git"
        ) from error
    except GitTimeout as error:
        # A hang is not a repository problem, so it does not get git's stderr
        # treatment — it gets its own message, which names the usual causes.
        raise AttributionError(str(error)) from error
    if result.returncode != 0:
        raise AttributionError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def ensure_repo(path: Path) -> Path:
    """Resolve ``path`` to a repository root, refusing non-repositories.

    Raises AttributionError naming the problem (mirroring the doctor
    git-hooks check's "not a git repository" wording).
    """
    root = Path(path).resolve()
    if not root.exists():
        raise AttributionError(f"repository path does not exist: {root}")
    try:
        top = run_git(root, "rev-parse", "--show-toplevel").strip()
    except AttributionError as error:
        raise AttributionError(f"not a git repository: {root}") from error
    return Path(top)


def normalise_repo_path(repo: Path, raw: str) -> str:
    """Validate a worktree-relative path and return it in git's posix form.

    Refuses absolute paths and ``..`` escapes so an RPC caller cannot read
    files outside the repository. Raises AttributionError on escape.
    """
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise AttributionError(
            f"path must be worktree-relative and stay inside the repository: {raw}"
        )
    posix = candidate.as_posix()
    if posix.startswith("/") or posix.split("/")[0] == "..":
        raise AttributionError(
            f"path must be worktree-relative and stay inside the repository: {raw}"
        )
    return posix


def epoch_to_iso(epoch: str) -> str:
    """git's epoch-seconds -> ISO 8601 UTC, matching ledger timestamp style."""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
