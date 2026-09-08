"""Trust score with full decomposition (FR-M37-03; F1 Workstream E task 21).

FR-M37-03: a trust score per agent per task class, extending the FR-M17-01
trust score, derived from the ledger on demand (FR-M17-05 — no metrics
database). Every component is reported with its evidence; the score can
never hide a bad component behind the aggregate, and an empty sample is
**insufficient evidence, never zero**.

Components and what the ledger supports:

* **first-pass yield** — proposed changes (``diff`` entries by the agent)
  never rejected: 1 - rejected/proposed;
* **rejection rate** — rejected/proposed over the same sample, where
  *rejected* is the F0 linked-rejection shape (the sequence is carried by
  a ``rejection`` entry) OR the entry's own decision is
  ``rejected``/``reworked``;
* **calibration error** — mean |confidence - outcome| over the agent's
  ``diff`` entries that carry a ``confidence`` value (the schema's
  self-reported, uncalibrated column), outcome 1.0 when the change stood,
  0.0 when rejected. When NO in-scope diff carries confidence the
  component is **unknown** — the ledger does not record confidence for
  this agent/class, and the number is never fabricated;
* **post-merge revert rate** — the rejection detector's ``reverted``
  shape over merged changes: ``diff`` entries whose decision is
  ``approved``, counting those whose sequence is carried by a reverted-
  shape rejection entry;
* **incident linkage** — **unknown**: the ledger carries no incident
  entry type to link against. The component stays visible with status
  ``unknown`` rather than being dropped from the decomposition.

Weighted combination (documented here as the brief requires):
first-pass yield 0.30, rejection rate 0.25, calibration error 0.20,
post-merge revert rate 0.15, incident linkage 0.10. Each component feeds
the score as a *goodness* (yield as-is; every rate/error as 1 - value).
The score is the weight-renormalised mean over the components that HAVE
evidence; components without evidence contribute nothing and are listed
in the decomposition. ``status`` is ``ok`` when every component has
evidence, ``partial`` when at least one does, and
``insufficient_evidence`` (with score null) when none does.

Task classes: the ledger carries no task-class column, so classes come
from the caller (``task_class_by_story`` mapping story id -> class;
stories without an entry are ``unclassified``), optionally restricted to
one ``task_class``.

Zero model calls (FR-M36-07): arithmetic over ledger rows.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .reasons import detection_shape

__all__ = ["SCORE_WEIGHTS", "compute_trust_score"]

SCORE_WEIGHTS = {
    "firstPassYield": 0.30,
    "rejectionRate": 0.25,
    "calibrationError": 0.20,
    "postMergeRevertRate": 0.15,
    "incidentLinkage": 0.10,
}

_STATUS_OK = "ok"
_STATUS_INSUFFICIENT = "insufficient_evidence"
_STATUS_UNKNOWN = "unknown"

REJECTED_DECISIONS = ("rejected", "reworked")
REVERTED_SHAPE = "reverted"


def _component(
    status: str,
    value: float | None,
    sample_size: int,
    **extra: Any,
) -> dict[str, Any]:
    component: dict[str, Any] = {
        "status": status,
        "value": value,
        "sampleSize": sample_size,
    }
    component.update(extra)
    return component


def compute_trust_score(
    ledger,
    *,
    actor_id: str,
    repo_id: str | None = None,
    task_class: str | None = None,
    task_class_by_story: dict[str, str] | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
) -> dict[str, Any]:
    """The FR-M37-03 trust score for one agent (optionally one task class)
    with its full decomposition. ``task_class_by_story`` maps story ids to
    task classes; without it every story is ``unclassified``."""
    scope = {
        "repoId": repo_id,
        "actorId": actor_id,
        "taskClass": task_class,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }

    def in_class(story_id: str) -> bool:
        if task_class is None:
            return True
        mapped = (task_class_by_story or {}).get(story_id, "unclassified")
        return mapped == task_class

    rows = ledger.query(
        action_type="diff",
        actor_id=actor_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        limit=1000,
    )
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]
    rows = [row for row in rows if in_class(row["story_id"])]

    rejection_rows = ledger.query(action_type="rejection", limit=1000)
    if repo_id is not None:
        rejection_rows = [
            row for row in rejection_rows if row.get("repo_id") == repo_id
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
    reverted_sequences = {
        row["rejected_sequence"]
        for row in rejection_rows
        if row.get("rejected_sequence") is not None
        and detection_shape(row) == REVERTED_SHAPE
    }

    def rejected(row: dict[str, Any]) -> bool:
        return row["seq"] in rejected_sequences or row.get("decision") in REJECTED_DECISIONS

    proposed = len(rows)
    rejected_count = sum(1 for row in rows if rejected(row))

    if proposed:
        rate = round(rejected_count / proposed, 6)
        yield_component = _component(
            _STATUS_OK, round(1 - rate, 6), proposed, rejected=rejected_count
        )
        rate_component = _component(_STATUS_OK, rate, proposed, rejected=rejected_count)
    else:
        yield_component = _component(
            _STATUS_INSUFFICIENT,
            None,
            0,
            note="no proposed changes in scope",
        )
        rate_component = _component(
            _STATUS_INSUFFICIENT,
            None,
            0,
            note="no proposed changes in scope",
        )

    confident = [
        (float(row["confidence"]), 0.0 if rejected(row) else 1.0)
        for row in rows
        if row.get("confidence") is not None
    ]
    if confident:
        error = sum(abs(conf - outcome) for conf, outcome in confident) / len(confident)
        calibration_component = _component(
            _STATUS_OK, round(error, 6), len(confident)
        )
    elif proposed:
        calibration_component = _component(
            _STATUS_UNKNOWN,
            None,
            0,
            note="no in-scope change carries a confidence value",
        )
    else:
        calibration_component = _component(
            _STATUS_INSUFFICIENT,
            None,
            0,
            note="no proposed changes in scope",
        )

    approved = [row for row in rows if row.get("decision") == "approved"]
    reverted = [row for row in approved if row["seq"] in reverted_sequences]
    if approved:
        revert_component = _component(
            _STATUS_OK,
            round(len(reverted) / len(approved), 6),
            len(approved),
            reverted=len(reverted),
        )
    else:
        revert_component = _component(
            _STATUS_INSUFFICIENT,
            None,
            0,
            note="no approved (merged) changes in scope",
        )

    incident_component = _component(
        _STATUS_UNKNOWN,
        None,
        0,
        note="the ledger carries no incident entry type to link against",
    )

    components = {
        "firstPassYield": yield_component,
        "rejectionRate": rate_component,
        "calibrationError": calibration_component,
        "postMergeRevertRate": revert_component,
        "incidentLinkage": incident_component,
    }

    weighted = 0.0
    weight_total = 0.0
    coverage: list[str] = []
    for name, weight in SCORE_WEIGHTS.items():
        component = components[name]
        if component["status"] != _STATUS_OK:
            continue
        goodness = (
            component["value"]
            if name == "firstPassYield"
            else 1 - component["value"]
        )
        weighted += weight * goodness
        weight_total += weight
        coverage.append(name)

    if weight_total:
        score: float | None = round(weighted / weight_total, 6)
        status = _STATUS_OK if len(coverage) == len(SCORE_WEIGHTS) else "partial"
    else:
        score = None
        status = _STATUS_INSUFFICIENT

    return {
        "scope": scope,
        "agentId": actor_id,
        "taskClass": task_class if task_class is not None else "all",
        "score": score,
        "status": status,
        "coverage": coverage,
        "components": components,
    }
