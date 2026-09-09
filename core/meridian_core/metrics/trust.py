"""Ledger-derived trust metrics (FR-M17-05; F0 Workstream F task 30).

FR-M17-05: every KPI is derivable from the ledger — there is no separate
metrics database. The rejection rate therefore recomputes from ledger
entries on demand and caches in-process, with invalidation on append (the
sidecar clears the cache from its ledger.append handler; the cache key
also carries the ledger tip sequence, so a missed clear still cannot serve
stale numbers).

Derivation, deliberately simple and auditable:

* a *proposed change* is a ledger entry with action_type "diff";
* a proposed change is *rejected* when its sequence appears as
  ``rejected_sequence`` on a "rejection" entry in scope (task 28's
  capture). Rejection entries whose rejected_sequence is null rejected
  untracked work — they name no proposed entry and cannot enter the
  numerator;
* rate = rejected / proposed (0 when nothing was proposed);
* every metric reports the greenfield/brownfield split (G6): proposed
  entries group by story, each story is classified by the caller-supplied
  classifier, and the buckets aggregate. Stories the classifier declines
  (no commit data) land in ``unclassified`` — reported, never dropped.

Task 19 (FR-M37-01) extends the scopes the rate is reported over,
additively — the F0 keys keep their meaning exactly:

* ``phase`` / ``action_type`` parameters restrict every scope;
* ``byActionClass`` / ``byPhase`` / ``byStory`` generalise "rejected" to
  every in-scope ledger entry (not only diffs): an entry counts as
  rejected when its sequence is carried by a rejection entry (the F0
  shape — post-merge reverts and captured rejections) OR its own
  ``decision`` is ``rejected``/``reworked`` (rejected in review, sent
  back for rework — the shapes a diff-link cannot see).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .coverage import (
    ATTACH_KEY,
    INSUFFICIENT_COVERAGE,
    attribution_coverage,
    envelope_for,
    ledger_row_attribution_state,
    scan_scope,
)

__all__ = ["TrustMetricsCache", "compute_rejection_rate"]

GREENFIELD = "greenfield"
BROWNFIELD = "brownfield"
UNCLASSIFIED = "unclassified"

#: Cache bound — the cache is a per-process optimisation, not a store.
_CACHE_MAX_ENTRIES = 64


class TrustMetricsCache:
    """In-process cache for derived trust metrics (FR-M17-05).

    Keys are supplied by the caller (the server keys on scope + ledger
    tip); eviction is plain FIFO past ``_CACHE_MAX_ENTRIES``.
    """

    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self._max = max_entries
        self._entries: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._entries.get(key)

    def put(self, key: str, value: Any) -> None:
        if key not in self._entries and len(self._entries) >= self._max:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[key] = value

    def invalidate(self) -> None:
        """Dropped on every ledger append: derived numbers may not outlive
        the facts they derive from."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def _bucket() -> dict[str, Any]:
    return {"proposed": 0, "rejected": 0, "rate": 0.0}


def _add(bucket: dict[str, Any], rejected: bool) -> None:
    bucket["proposed"] += 1
    if rejected:
        bucket["rejected"] += 1


def _rates(bucket: dict[str, Any]) -> dict[str, Any]:
    if bucket["proposed"]:
        bucket["rate"] = round(bucket["rejected"] / bucket["proposed"], 6)
    return bucket


def compute_rejection_rate(
    ledger,
    *,
    repo_id: str | None = None,
    story_id: str | None = None,
    actor_id: str | None = None,
    phase: str | None = None,
    action_type: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    classify: Callable[[str], str | None] | None = None,
    attribution_floor: float | None = None,
) -> dict[str, Any]:
    """Rejection rate per agent, per repository, split greenfield/brownfield.

    ``classify`` maps a story id to GREENFIELD/BROWNFIELD or None
    (unclassified); absent entirely, everything lands in unclassified.
    ``phase`` and ``action_type`` restrict every scope (FR-M37-01, task 19).
    The result additionally carries ``byActionClass`` / ``byPhase`` /
    ``byStory`` — the generalised scopes over every in-scope entry, where
    an entry is rejected on a linked rejection entry OR a
    rejected/reworked decision of its own.

    FR-M41-06: ``attribution_floor`` (the governance pack's
    ``attributionCoverageFloor``, plumbed by the RPC layer) suppresses
    the headline rate — it reads ``insufficient_coverage`` with no value —
    when the attributed share of the proposed-change population falls
    below the floor. A metric over a population it cannot attribute is
    not evidence (P25).
    """
    scope = {
        "repoId": repo_id,
        "storyId": story_id,
        "actorId": actor_id,
        "phase": phase,
        "actionType": action_type,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }
    # FR-M41-07 (D36): full-history scans over the after_sequence cursor —
    # no 1,000-row cap anywhere; the coverage envelope on the result
    # reports what the figure saw (FR-M41-08).
    rows, _diff_available = scan_scope(
        ledger,
        action_type="diff",
        story_id=story_id,
        actor_id=actor_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )
    all_rows, all_available = scan_scope(
        ledger,
        story_id=story_id,
        actor_id=actor_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]
        all_rows = [row for row in all_rows if row.get("repo_id") == repo_id]
    if phase is not None:
        rows = [row for row in rows if row.get("phase") == phase]
        all_rows = [row for row in all_rows if row.get("phase") == phase]
    if action_type is not None:
        all_rows = [row for row in all_rows if row.get("action_type") == action_type]
    rejection_rows, rejection_available = scan_scope(
        ledger, action_type="rejection"
    )
    if repo_id is not None:
        rejection_rows = [
            row for row in rejection_rows if row.get("repo_id") == repo_id
        ]
    if story_id is not None:
        rejection_rows = [
            row for row in rejection_rows if row.get("story_id") == story_id
        ]
    if from_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] >= from_sequence
        ]
    if to_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] <= to_sequence
        ]
    rejected_sequences = {
        row["rejected_sequence"]
        for row in rejection_rows
        if row.get("rejected_sequence") is not None
    }

    overall = _bucket()
    split = {GREENFIELD: _bucket(), BROWNFIELD: _bucket(), UNCLASSIFIED: _bucket()}
    by_agent: dict[str, dict[str, Any]] = {}
    for row in rows:
        rejected = row["seq"] in rejected_sequences
        _add(overall, rejected)
        agent = by_agent.setdefault(row["actor_id"], _bucket())
        _add(agent, rejected)
        if classify is None:
            kind = UNCLASSIFIED
        else:
            kind = classify(row["story_id"]) or UNCLASSIFIED
            if kind not in split:
                kind = UNCLASSIFIED
        _add(split[kind], rejected)

    # Generalised FR-M37-01 scopes: every in-scope entry except the
    # rejection-capture entries themselves (a "rejection" entry records a
    # rejection — counting its own decision would double-count), where
    # "rejected" also covers the entry's own rejected/reworked decision.
    by_class: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, dict[str, Any]] = {}
    by_story: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        if row["action_type"] == "rejection":
            continue
        rejected = row["seq"] in rejected_sequences or row.get("decision") in (
            "rejected",
            "reworked",
        )
        _add(by_class.setdefault(row["action_type"], _bucket()), rejected)
        _add(by_phase.setdefault(row["phase"], _bucket()), rejected)
        _add(by_story.setdefault(row["story_id"], _bucket()), rejected)

    # FR-M41-08 (NFR-34): the disclosure rides the same result, never
    # a separate call. The primary population is every in-scope row
    # (the broadest view the result reports); the rejection lookup is
    # an auxiliary scan — a capped lookup truncates the figure too.
    # FR-M41-06: the attribution dimension covers the proposed-change
    # population the rate derives from; below the configured floor the
    # headline rate reads insufficient_coverage and shows no value.
    row_states = [ledger_row_attribution_state(row) for row in rows]
    coverage_check = attribution_coverage(row_states, attribution_floor)
    below_floor = coverage_check.belowFloor
    rate_value = None if below_floor else _rates(overall)["rate"]
    envelope = envelope_for(
        rate_value,
        all_rows,
        all_available,
        aux_scans=((rejection_rows, rejection_available),),
        attribution_states=row_states,
        attribution_floor=attribution_floor,
    )
    return {
        "scope": scope,
        "proposed": overall["proposed"],
        "rejected": overall["rejected"],
        "rate": rate_value,
        "status": INSUFFICIENT_COVERAGE if below_floor else "ok",
        "split": {kind: _rates(bucket) for kind, bucket in split.items()},
        "byAgent": {agent: _rates(bucket) for agent, bucket in sorted(by_agent.items())},
        "byActionClass": {
            key: _rates(bucket) for key, bucket in sorted(by_class.items())
        },
        "byPhase": {key: _rates(bucket) for key, bucket in sorted(by_phase.items())},
        "byStory": {key: _rates(bucket) for key, bucket in sorted(by_story.items())},
        "coverageNote": (
            "attribution coverage below the configured floor "
            f"({coverage_check.coverage} < {coverage_check.floor}) "
            "— the rate reads insufficient_coverage and shows no value "
            "(FR-M41-06)"
            if below_floor
            else None
        ),
        ATTACH_KEY: envelope.to_dict(),
    }
