"""The classifier itself — see the package docstring for the rule."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..attribution import blame as blame_mod
from ..attribution import diff as diff_mod
from ..attribution._git import AttributionError, ensure_repo, run_git
from ..rejection.detector import EMPTY_TREE

__all__ = [
    "BROWNFIELD",
    "Classification",
    "DEFAULT_MAX_MEDIAN_AGE_DAYS",
    "DEFAULT_NEW_FILE_RATIO_THRESHOLD",
    "GREENFIELD",
    "classify",
]

GREENFIELD = "greenfield"
BROWNFIELD = "brownfield"

#: Default ``meridian.greenfieldNewFileRatio``.
DEFAULT_NEW_FILE_RATIO_THRESHOLD = 0.5
#: Default ``meridian.greenfieldMaxMedianAgeDays``.
DEFAULT_MAX_MEDIAN_AGE_DAYS = 30.0

_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Classification:
    new_files: int
    modified_files: int
    new_file_ratio: float
    median_touched_code_age_days: float | None
    classification: str  # GREENFIELD | BROWNFIELD


def _iso_to_epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _story_commits(
    repo: Path, commits: list[str] | None, base: str | None, compare: str | None
) -> list[str]:
    """Resolve the story's commit list to full shas, oldest first."""
    if commits:
        resolved: list[str] = []
        for raw in commits:
            sha = run_git(repo, "rev-parse", "--verify", f"{raw}^{{commit}}").strip()
            if sha not in resolved:
                resolved.append(sha)
        return resolved
    if base and compare:
        out = run_git(
            repo, "rev-list", "--no-merges", "--reverse", f"{base}..{compare}"
        )
        return [line for line in out.splitlines() if line]
    raise AttributionError(
        "classify needs either a commits list or both base and compare"
    )


def classify(
    repo_path: Path | str,
    commits: list[str] | None = None,
    base: str | None = None,
    compare: str | None = None,
    *,
    new_file_ratio_threshold: float = DEFAULT_NEW_FILE_RATIO_THRESHOLD,
    max_median_age_days: float = DEFAULT_MAX_MEDIAN_AGE_DAYS,
) -> Classification:
    """Classify a story/session's changes as greenfield or brownfield."""
    repo = ensure_repo(Path(repo_path))
    if not 0 < new_file_ratio_threshold <= 1:
        raise AttributionError(
            f"new_file_ratio_threshold must be in (0, 1], got {new_file_ratio_threshold}"
        )
    if not 0 < max_median_age_days <= 36_500:
        raise AttributionError(
            f"max_median_age_days must be in (0, 36500], got {max_median_age_days}"
        )

    added_paths: set[str] = set()
    modified_paths: set[str] = set()
    ages_days: list[float] = []  # one entry per pre-existing line the story changed

    for sha in _story_commits(repo, commits, base, compare):
        parents = run_git(repo, "log", "-1", "--format=%P", sha).split()
        diff_base = parents[0] if parents else EMPTY_TREE
        commit_epoch = int(run_git(repo, "log", "-1", "--format=%ct", sha).strip())
        files = diff_mod.diff(repo, base=diff_base, compare=sha)
        blame_cache: dict[str, dict[int, float]] = {}
        for file in files:
            removed = [
                line
                for hunk in file.hunks
                for line in hunk.lines
                if line.kind == "removed"
            ]
            if file.status == "added":
                added_paths.add(file.path)
                continue
            # modified, renamed or deleted: the file existed before the story.
            modified_paths.add(file.path)
            if not parents or not removed:
                continue
            blame_path = file.old_path or file.path
            if blame_path not in blame_cache:
                lines = blame_mod.blame(repo, ref=diff_base, paths=[blame_path])
                blame_cache[blame_path] = {
                    line.line: _iso_to_epoch(line.author_time) for line in lines
                }
            introduced = blame_cache[blame_path]
            for line in removed:
                origin = introduced.get(line.old_line)
                if origin is None:
                    continue  # defensive: blame/diff disagreement, skip the line
                ages_days.append((commit_epoch - origin) / _SECONDS_PER_DAY)

    denominator = len(added_paths) + len(modified_paths)
    new_file_ratio = len(added_paths) / denominator if denominator else 0.0
    median_age = statistics.median(ages_days) if ages_days else None
    is_greenfield = (
        new_file_ratio >= new_file_ratio_threshold
        or (median_age is not None and median_age < max_median_age_days)
    )
    return Classification(
        new_files=len(added_paths),
        modified_files=len(modified_paths),
        new_file_ratio=round(new_file_ratio, 6),
        median_touched_code_age_days=round(median_age, 6) if median_age is not None else None,
        classification=GREENFIELD if is_greenfield else BROWNFIELD,
    )
