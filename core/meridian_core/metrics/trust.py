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
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    classify: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Rejection rate per agent, per repository, split greenfield/brownfield.

    ``classify`` maps a story id to GREENFIELD/BROWNFIELD or None
    (unclassified); absent entirely, everything lands in unclassified.
    """
    scope = {
        "repoId": repo_id,
        "storyId": story_id,
        "actorId": actor_id,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }
    rows = ledger.query(
        action_type="diff",
        story_id=story_id,
        actor_id=actor_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        limit=1000,
    )
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]
    rejection_rows = ledger.query(action_type="rejection", limit=1000)
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

    return {
        "scope": scope,
        "proposed": overall["proposed"],
        "rejected": overall["rejected"],
        "rate": _rates(overall)["rate"],
        "split": {kind: _rates(bucket) for kind, bucket in split.items()},
        "byAgent": {agent: _rates(bucket) for agent, bucket in sorted(by_agent.items())},
    }
