"""Rejection-reason distribution per agent (FR-M37-02; F1 Workstream E task 20).

FR-M37-02: every rejection carries a reason from the E-GR-03 taxonomy and
the team sees *why* an agent's work is rejected, not only how often. The
distribution derives from the ledger on demand (FR-M17-05 — no metrics
database) and reuses the same in-process cache + append invalidation as
the other trust metrics.

Grouping rules, kept honest about what the ledger carries:

* the unit is a ``rejection`` entry; its class is ``rework_reason`` —
  fail-closed: a missing class reports the taxonomy default (``other``),
  never a null or a fabricated class;
* the *agent* a rejection is attributed to is the author of the rejected
  change: the entry's ``rejected_sequence`` resolves the source entry and
  its ``actor_id``; when the link is absent (untracked external work) the
  rejection entry's own ``actor_id`` is used and no row is dropped;
* the detection shape (``reverted`` / ``force_amended`` /
  ``replaced_within_window``) is read from the entry's ``tool_calls``
  payload when present — the mechanical shape taxonomy.module.detector
  produced — and omitted when absent;
* the greenfield/brownfield split (G6) classifies each rejection by its
  story through the caller-supplied classifier; unclassifiable stories
  land in ``unclassified``, reported, never dropped.

Zero model calls (FR-M36-07): string normalisation over ledger rows.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..rejection.taxonomy import load_taxonomy
from .coverage import ATTACH_KEY, envelope_for, scan_scope

__all__ = ["compute_reason_distribution", "detection_shape"]

GREENFIELD = "greenfield"
BROWNFIELD = "brownfield"
UNCLASSIFIED = "unclassified"


def detection_shape(row: dict[str, Any]) -> str | None:
    """The mechanical detection shape stored in a rejection entry's
    ``tool_calls`` payload (task 28's capture), or None when absent."""
    raw = row.get("tool_calls")
    if isinstance(raw, str) and raw:
        try:
            detail = json.loads(raw)
        except ValueError:
            return None
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):
            shape = detail[0].get("shape")
            if isinstance(shape, str):
                return shape
    return None


def _distribution() -> dict[str, Any]:
    return {"total": 0, "byClass": {}}


def _add(dist: dict[str, Any], reason: str) -> None:
    dist["total"] += 1
    classes = dist["byClass"]
    classes[reason] = classes.get(reason, 0) + 1


def _rates(dist: dict[str, Any]) -> dict[str, Any]:
    total = dist["total"]
    dist["byClass"] = {
        reason: {"count": count, "rate": round(count / total, 6) if total else 0.0}
        for reason, count in sorted(dist["byClass"].items())
    }
    return dist


def compute_reason_distribution(
    ledger,
    *,
    repo_id: str | None = None,
    actor_id: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    classify: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """E-GR-03 reason distribution overall, per agent, per shape, with the
    greenfield/brownfield split. ``classify`` maps a story id to
    GREENFIELD/BROWNFIELD or None (unclassified)."""
    scope = {
        "repoId": repo_id,
        "actorId": actor_id,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }
    default_class = load_taxonomy().default.id
    # FR-M41-07 (D36): the full rejection history over the after_sequence
    # cursor; the repo filter below is a declared scope restriction, so
    # the envelope's population stays the whole scanned scope
    # (FR-M41-08). rejected_sequence resolution is per-row point lookups
    # (seq is unique) — nothing there can truncate.
    rows, rows_available = scan_scope(
        ledger,
        action_type="rejection",
        actor_id=actor_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )
    scoped_rows = rows
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]

    overall = _distribution()
    by_agent: dict[str, dict[str, Any]] = {}
    by_shape: dict[str, dict[str, Any]] = {}
    split = {GREENFIELD: _distribution(), BROWNFIELD: _distribution(), UNCLASSIFIED: _distribution()}

    for row in rows:
        reason = row.get("rework_reason") or default_class
        agent = row["actor_id"]
        rejected_sequence = row.get("rejected_sequence")
        if rejected_sequence is not None:
            source = ledger.get_entry(rejected_sequence)
            if source is not None and source.get("actor_id"):
                agent = source["actor_id"]
        if actor_id is not None and agent != actor_id:
            continue  # agent scope filters on the RESOLVED author

        _add(overall, reason)
        _add(by_agent.setdefault(agent, _distribution()), reason)
        shape = detection_shape(row)
        if shape is not None:
            _add(by_shape.setdefault(shape, _distribution()), reason)
        if classify is None:
            kind = UNCLASSIFIED
        else:
            kind = classify(row["story_id"]) or UNCLASSIFIED
            if kind not in split:
                kind = UNCLASSIFIED
        _add(split[kind], reason)

    return {
        "scope": scope,
        "total": overall["total"],
        "byClass": _rates(overall)["byClass"],
        "byShape": {shape: _rates(dist) for shape, dist in sorted(by_shape.items())},
        "byAgent": {agent: _rates(dist) for agent, dist in sorted(by_agent.items())},
        "split": {kind: _rates(dist) for kind, dist in split.items()},
        ATTACH_KEY: envelope_for(
            overall["total"], scoped_rows, rows_available
        ).to_dict(),
    }
