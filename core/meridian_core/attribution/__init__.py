"""Deterministic, git-native attribution engine (F0 Workstream C, task 13).

Maps changed lines to (commit, author identity, timestamp, content) with
nothing but the git CLI — no model calls, no network (FR-M33-02 subset,
FR-M36-07). ``blame`` covers committed state; ``diff`` covers uncommitted,
staged and range changes, and annotates range-diff added lines with blame
attribution taken at the compare ref.
"""

from ._git import AttributionError, ensure_repo, run_git

__all__ = ["AttributionError", "ensure_repo", "run_git"]
