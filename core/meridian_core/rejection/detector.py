"""Deterministic rejection detection from git history (FR-M37-01 subset).

The engine reuses the attribution diff/blame plumbing: every commit's added
and removed lines are path+content multisets, so detection is byte-exact
under CRLF (content is compared without line terminators, matching the
attribution engine's convention).
"""

from __future__ import annotations

from ..gitcmd import GitTimeout, run_git_command

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..attribution import blame as blame_mod
from ..attribution import diff as diff_mod
from ..attribution._git import AttributionError, ensure_repo, run_git
from ..trailers import MERIDIAN_LEDGER_KEY, parse_trailers

__all__ = [
    "DEFAULT_REJECTION_WINDOW_DAYS",
    "REASON_FORCE_AMENDED",
    "REASON_REPLACED_WITHIN_WINDOW",
    "REASON_REVERTED",
    "REJECTION_REASONS",
    "Rejection",
    "detect",
    "resolve_ledger_sequence",
]

#: Default ``meridian.rejectionWindowDays`` (the replaced-within-window shape).
DEFAULT_REJECTION_WINDOW_DAYS = 7

REASON_REVERTED = "reverted"
REASON_FORCE_AMENDED = "force_amended"
REASON_REPLACED_WITHIN_WINDOW = "replaced_within_window"
REJECTION_REASONS = (REASON_REVERTED, REASON_FORCE_AMENDED, REASON_REPLACED_WITHIN_WINDOW)

#: The well-known git empty tree — the parent of a root commit.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Rejection:
    """One detected rejection (before any ledger recording)."""

    rejected_commit: str  # full hex of the commit whose change was rejected
    rejecting_commit: str | None  # full hex of the commit that rejected it;
    # None for force_amended (the change vanished with the amend itself)
    reason: str  # one of REJECTION_REASONS
    paths: tuple[str, ...] = ()  # touched paths, sorted, deduplicated
    lines_rejected: int = 0  # added lines of the change that were removed
    rejected_at: str | None = None  # ISO 8601 UTC of the rejecting commit


@dataclass
class _PendingChange:
    commit: str
    date_epoch: int
    added: Counter  # (path, content) -> count, from the change's own diff
    removed: Counter  # (path, content) -> count


def _commit_diff(repo: Path, sha: str) -> tuple[Counter, Counter, set[str]]:
    """One commit's added/removed line multisets and touched paths."""
    parents = run_git(repo, "log", "-1", "--format=%P", sha).split()
    base = parents[0] if parents else EMPTY_TREE
    files = diff_mod.diff(repo, base=base, compare=sha)
    added: Counter = Counter()
    removed: Counter = Counter()
    paths: set[str] = set()
    for file in files:
        paths.add(file.path)
        if file.old_path:
            paths.add(file.old_path)
        for hunk in file.hunks:
            for line in hunk.lines:
                if line.kind == "added":
                    added[(file.path, line.content)] += 1
                elif line.kind == "removed":
                    key = (file.old_path or file.path, line.content)
                    removed[key] += 1
    return added, removed, paths


def _line_multiset_at_ref(repo: Path, ref: str) -> Counter:
    """Every (path, content) present at ``ref`` — the liveness oracle."""
    lines = blame_mod.blame(repo, ref=ref)
    return Counter((line.path, line.content) for line in lines)


def _reachable_commits(repo: Path, base: str | None, ref: str) -> list[tuple[str, int]]:
    """(sha, committer epoch) for every non-merge commit, oldest first."""
    args = ["log", "--no-merges", "--format=%H%x1f%ct", "--reverse"]
    args.append(f"{base}..{ref}" if base else ref)
    out = run_git(repo, *args)
    commits: list[tuple[str, int]] = []
    for record in out.splitlines():
        sha, _, epoch = record.partition("\x1f")
        if sha:
            commits.append((sha, int(epoch)))
    return commits


def _reflog_shas(repo: Path) -> list[str]:
    """Distinct shas ever pointed at by HEAD (amend/reset evidence).

    Reflogs can be disabled or absent (bare mirrors): an unreadable reflog
    yields no force-amend candidates rather than an error.
    """
    try:
        out = run_git(repo, "reflog", "--format=%H")
    except AttributionError:
        return []
    seen: dict[str, None] = {}
    for line in out.splitlines():
        if line.strip():
            seen.setdefault(line.strip(), None)
    return list(seen)


def _is_ancestor(repo: Path, sha: str, ref: str) -> bool:
    try:
        result = run_git_command(repo, "merge-base", "--is-ancestor", sha, ref)
    except (OSError, GitTimeout):
        # An ancestry question that cannot be answered is answered "no" — the
        # caller treats it as "not linked", which is the conservative reading.
        return False
    return result.returncode == 0


def _covers(whole: Counter, part: Counter) -> bool:
    """Multiset subset: every item of ``part`` fully accounted for in ``whole``."""
    return not (part - whole)


def detect(
    repo_path: Path | str,
    base: str | None = None,
    ref: str = "HEAD",
    window_days: int = DEFAULT_REJECTION_WINDOW_DAYS,
) -> list[Rejection]:
    """Detect rejections in ``base..ref`` (or the whole ref history).

    ``window_days`` bounds the replaced-within-window shape (the
    ``meridian.rejectionWindowDays`` setting, default 7). Reverts and
    force-amends are unconditional.
    """
    repo = ensure_repo(Path(repo_path))
    if not 1 <= window_days <= 3650:
        raise AttributionError(
            f"window_days must be between 1 and 3650, got {window_days}"
        )
    window_seconds = window_days * _SECONDS_PER_DAY
    rejections: list[Rejection] = []
    pending: list[_PendingChange] = []

    for sha, epoch in _reachable_commits(repo, base, ref):
        try:
            added, removed, _paths = _commit_diff(repo, sha)
        except AttributionError:
            continue  # unparseable commit: skip, never crash detection
        survivors: list[_PendingChange] = []
        for change in pending:
            if _covers(removed, change.added):
                # Every line this change added is removed by `sha`: classify.
                restored = bool(change.removed) and _covers(added, change.removed)
                if restored:
                    rejections.append(_rejection(change, sha, epoch, REASON_REVERTED))
                elif epoch - change.date_epoch <= window_seconds:
                    rejections.append(
                        _rejection(change, sha, epoch, REASON_REPLACED_WITHIN_WINDOW)
                    )
                # else: the change stood past the window — evolution, keep
                # no record and drop it from the pending set either way.
            else:
                survivors.append(change)
        pending = survivors
        if added:
            pending.append(
                _PendingChange(commit=sha, date_epoch=epoch, added=added, removed=removed)
            )

    rejections.extend(_detect_force_amends(repo, base, ref))
    rejections.sort(key=lambda r: (r.rejected_commit, r.reason))
    return rejections


def _rejection(
    change: _PendingChange,
    rejecting: str,
    epoch: int,
    reason: str,
) -> Rejection:
    from ..attribution._git import epoch_to_iso

    return Rejection(
        rejected_commit=change.commit,
        rejecting_commit=rejecting,
        reason=reason,
        paths=tuple(sorted({path for path, _content in change.added})),
        lines_rejected=sum(change.added.values()),
        rejected_at=epoch_to_iso(str(epoch)),
    )


def _detect_force_amends(
    repo: Path, base: str | None, ref: str
) -> list[Rejection]:
    """Commits that were once HEAD but are unreachable now, whose added
    content no longer exists at ``ref`` — force-amended or reset away."""
    reachable = {sha for sha, _epoch in _reachable_commits(repo, base, ref)}
    live = _line_multiset_at_ref(repo, ref)
    found: list[Rejection] = []
    for sha in _reflog_shas(repo):
        if sha in reachable or _is_ancestor(repo, sha, ref):
            continue
        try:
            added, removed, paths = _commit_diff(repo, sha)
        except AttributionError:
            continue  # reflog garbage-collected or unparseable: skip
        if not added:
            continue
        if added - live:
            from ..attribution._git import epoch_to_iso

            epoch = int(run_git(repo, "log", "-1", "--format=%ct", sha).strip())
            found.append(
                Rejection(
                    rejected_commit=sha,
                    rejecting_commit=None,
                    reason=REASON_FORCE_AMENDED,
                    paths=tuple(sorted({path for path, _ in added})),
                    lines_rejected=sum(added.values()),
                    rejected_at=epoch_to_iso(str(epoch)),
                )
            )
    return found


def resolve_ledger_sequence(repo: Path | str, commit: str) -> int | None:
    """The ledger sequence a commit's ``Meridian-Ledger`` trailer points at.

    The trailer carries a ``from-to`` range recorded for the commit's
    changes; the first sequence is the rejected entry's sequence. Absent
    trailer or unparsable range: None (the rejection records the commit
    alone).
    """
    repo = Path(repo)
    try:
        body = run_git(repo, "log", "-1", "--format=%B", commit)
    except AttributionError:
        return None
    for key, value in parse_trailers(body):
        if key != MERIDIAN_LEDGER_KEY:
            continue
        first, _, _last = value.partition("-")
        try:
            return int(first.strip())
        except ValueError:
            return None
    return None
