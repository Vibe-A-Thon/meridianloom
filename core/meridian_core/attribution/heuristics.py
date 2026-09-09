"""Human vs. agent change heuristics (FR-M35-02 attribution aid; gaps G3).

Deterministic, rule-based classification of working-tree changes. Every
conclusion is labelled and the label is honest about its evidence:

* burst size — lines added in one timestamp-second sweep. Agents writing
  files produce same-second multi-file bursts; humans rarely save three
  files in the same second.
* multi-line insertion rate — fraction of insertion hunks that add >=5
  lines at once. Editors insert incrementally; file-writing agents insert
  in blocks.
* new-file size — a brand-new file of >=25 lines appearing in one write.
* observed-session cross-reference — an active observed agent session that
  covers the edit window raises the agent weight and lifts the label to
  ``telemetry``; without it the floor is ``inferred``.

Keystroke cadence is deliberately NOT a signal: an agent acting via file
writes leaves no keystroke telemetry at all, and git/filesystem observation
cannot see inter-keystroke timing. The heuristic therefore reasons about
burst/timing patterns from fs/git timestamps only — mtime granularity for
the worktree, commit grouping for ranges.

G3: results degrade, never silently. ``unattributed`` is a first-class
answer when no signal fires (FR-M41-04/05; P26); heuristic output is
never labelled better than ``telemetry`` and the default floor is
``inferred`` — labelled, never presented as fact. Zero model calls
(FR-M36-07).
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import diff as diff_mod
from ._git import ensure_repo
from .states import (
    ATTRIBUTION_UNATTRIBUTED,
    UNKNOWN_REASON_EXCLUDED_PATH,
    UNKNOWN_REASON_NO_SIGNAL,
    UNKNOWN_REASON_VOCABULARY_VERSION,
    decide_attribution,
)

__all__ = ["FileClassification", "ClassificationResult", "classify", "classify_with_repo"]

# Thresholds, in one place, so behaviour is auditable in a single read.
_BURST_AGENT = 10  # lines in one sweep -> agent +1
_BURST_AGENT_STRONG = 40  # lines in one sweep -> agent +2
_MULTI_LINE_MIN = 5  # an insertion hunk of >=5 lines counts as a block
_RATE_AGENT = 0.75  # multi-line rate above this -> agent +1
_RATE_HUMAN = 0.25  # below this -> human +1
_NEW_FILE_AGENT = 25  # a new file with >= this many lines -> agent +1
_SMALL_CHANGE = 5  # fewer added lines than this -> human +1
_SAME_SECOND_FILES = 3  # >= this many files in one second -> agent +1
_OBSERVED_BONUS = 2  # covering observed session -> agent +2


@dataclass(frozen=True)
class FileClassification:
    path: str
    lines_added: int
    lines_removed: int
    burst_lines: int  # lines added in the same sweep as this file's edits
    multi_line_insert_rate: float
    edit_timestamp: str | None  # ISO 8601 UTC from fs mtime; null for deletes
    attribution: str  # agent | human | unattributed (FR-M41-04)
    unknown_reason: str | None  # closed vocabulary when unattributed (FR-M41-05)
    unknown_reason_version: int  # vocabulary version recorded with the answer
    agent_weight: float  # 0.0 human .. 1.0 agent; 0.5 = no evidence
    observation_confidence: str  # telemetry (observed session) | inferred
    rationale: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClassificationResult:
    repo_path: str
    files: list[FileClassification]


def _edit_timestamp(repo: Path, path: str) -> tuple[float, str] | None:
    try:
        mtime = os.stat(repo / path).st_mtime
    except OSError:
        return None
    return mtime, datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _session_started_epoch(session: dict[str, Any]) -> float | None:
    started = session.get("startedAt")
    if started is None:
        return None
    if isinstance(started, (int, float)) and not isinstance(started, bool):
        return float(started)
    if isinstance(started, str):
        try:
            return datetime.fromisoformat(started).timestamp()
        except ValueError:
            return None
    return None


def _session_covers(
    session: dict[str, Any], mtime: float | None
) -> bool:
    started = _session_started_epoch(session)
    # A session without a start time is treated as currently active; with
    # one, the file must have been touched after it began.
    return started is None or (mtime is not None and mtime >= started)


def _is_excluded(path: str, patterns: list[str]) -> bool:
    """``excluded_path`` matching: an exact worktree-relative path, a
    directory prefix (``dist/``), or an fnmatch glob (``*.lock``)."""
    for pattern in patterns:
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue
        if path == pattern or path.startswith(pattern + "/"):
            return True
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
            path.rsplit("/", 1)[-1], pattern
        ):
            return True
    return False


def classify(
    repo_path: Path | str,
    base: str | None = None,
    compare: str | None = None,
    staged: bool = False,
    paths: list[str] | None = None,
    observed_sessions: list[dict[str, Any]] | None = None,
    excluded_paths: list[str] | None = None,
) -> list[FileClassification]:
    """Classify each changed file as agent/human/unattributed (FR-M41-04).

    ``excluded_paths`` marks paths excluded from attribution: matching
    files report ``unattributed``/``excluded_path`` — excluded is
    reported, never silently dropped (FR-M41-05).
    """
    _, files = classify_with_repo(
        repo_path,
        base=base,
        compare=compare,
        staged=staged,
        paths=paths,
        observed_sessions=observed_sessions,
        excluded_paths=excluded_paths,
    )
    return files


def classify_with_repo(
    repo_path: Path | str,
    base: str | None = None,
    compare: str | None = None,
    staged: bool = False,
    paths: list[str] | None = None,
    observed_sessions: list[dict[str, Any]] | None = None,
    excluded_paths: list[str] | None = None,
) -> tuple[Path, ClassificationResult]:
    repo = ensure_repo(Path(repo_path))
    exclusions = [str(p) for p in (excluded_paths or []) if str(p).strip()]
    file_diffs = diff_mod.diff(
        repo, base=base, compare=compare, staged=staged, paths=paths
    )
    sessions = [s for s in (observed_sessions or []) if isinstance(s, dict)]

    # Per-file facts.
    stats: dict[str, dict[str, Any]] = {}
    for file in file_diffs:
        added = [
            line
            for hunk in file.hunks
            for line in hunk.lines
            if line.kind == "added"
        ]
        removed = [
            line
            for hunk in file.hunks
            for line in hunk.lines
            if line.kind == "removed"
        ]
        events = [
            hunk
            for hunk in file.hunks
            if any(line.kind == "added" for line in hunk.lines)
        ]
        multi = [
            hunk
            for hunk in events
            if sum(1 for line in hunk.lines if line.kind == "added")
            >= _MULTI_LINE_MIN
        ]
        rate = (len(multi) / len(events)) if events else 0.0
        stamp = _edit_timestamp(repo, file.path) if file.status != "deleted" else None
        mtime = stamp[0] if stamp else None
        # Burst grouping: committed lines group by introducing commit;
        # worktree lines group by filesystem mtime second.
        key = (
            next(
                (line.commit for line in added if line.commit),
                None,
            )
            if (base and compare)
            else (str(int(mtime)) if mtime is not None else None)
        )
        stats[file.path] = {
            "added": len(added),
            "removed": len(removed),
            "rate": rate,
            "is_new": file.status == "added",
            "mtime": mtime,
            "edit_timestamp": stamp[1] if stamp else None,
            "burst_key": key,
        }

    # Cross-file burst totals: everything written in the same sweep.
    burst_totals: dict[str, int] = {}
    for stat in stats.values():
        key = stat["burst_key"]
        if key is not None:
            burst_totals[key] = burst_totals.get(key, 0) + stat["added"]
    same_second_files = {
        key: sum(
            1 for stat in stats.values() if stat["burst_key"] == key
        )
        for key in burst_totals
    }

    results: list[FileClassification] = []
    for file in file_diffs:
        stat = stats[file.path]
        agent = 0
        human = 0
        rationale: list[str] = []

        burst = burst_totals.get(stat["burst_key"] or "", stat["added"])
        if burst >= _BURST_AGENT_STRONG:
            agent += 2
            rationale.append(f"burst of {burst} lines added in one timestamp sweep")
        elif burst >= _BURST_AGENT:
            agent += 1
            rationale.append(f"burst of {burst} lines added in one timestamp sweep")

        rate = stat["rate"]
        if rate >= _RATE_AGENT:
            agent += 1
            rationale.append(
                f"{rate:.0%} of insertions are multi-line blocks"
                f" (>= {_MULTI_LINE_MIN} lines at once)"
            )
        elif rate <= _RATE_HUMAN and stat["added"] > 0:
            human += 1
            rationale.append("incremental single-line edits dominate")

        if stat["is_new"] and stat["added"] >= _NEW_FILE_AGENT:
            agent += 1
            rationale.append(
                f"new file with {stat['added']} lines written in one pass"
            )

        key = stat["burst_key"]
        if (
            key is not None
            and same_second_files.get(key, 0) >= _SAME_SECOND_FILES
        ):
            agent += 1
            rationale.append(
                f"{same_second_files[key]} files written in the same second"
            )

        covering = [
            session
            for session in sessions
            if _session_covers(session, stat["mtime"])
        ]
        confidence = "inferred"
        if covering:
            agent += _OBSERVED_BONUS
            session = covering[0]
            confidence = "telemetry"
            rationale.append(
                "covered by observed session"
                f" {session.get('sessionId', '?')}"
                f" ({session.get('vendor', 'unknown vendor')})"
            )

        if 0 < stat["added"] < _SMALL_CHANGE:
            human += 1
            rationale.append(f"small change ({stat['added']} added lines)")

        # FR-M41-04: the three-state decision is positive-evidence-only, in
        # one auditable place — never "human = not agent".
        attribution, weight = decide_attribution(agent, human)
        unknown_reason: str | None = None
        if _is_excluded(file.path, exclusions):
            attribution, weight = ATTRIBUTION_UNATTRIBUTED, 0.5
            unknown_reason = UNKNOWN_REASON_EXCLUDED_PATH
            rationale.append("path excluded from attribution")
        elif attribution == ATTRIBUTION_UNATTRIBUTED:
            # No decisive signal fired (or agent/human evidence conflicted
            # in the middle band): the reason is recorded, never absorbed
            # into the nearest confident answer (FR-M41-05, P26).
            unknown_reason = UNKNOWN_REASON_NO_SIGNAL

        results.append(
            FileClassification(
                path=file.path,
                lines_added=stat["added"],
                lines_removed=stat["removed"],
                burst_lines=burst,
                multi_line_insert_rate=round(rate, 2),
                edit_timestamp=stat["edit_timestamp"],
                attribution=attribution,
                unknown_reason=unknown_reason,
                unknown_reason_version=UNKNOWN_REASON_VOCABULARY_VERSION,
                agent_weight=weight,
                observation_confidence=confidence,
                rationale=rationale,
            )
        )

    return repo, ClassificationResult(repo_path=str(repo), files=results)
