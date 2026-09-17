"""Accepted-change economics — FR-M45-01…04, AMD-M39, AC-51 (N2 Workstream F
tasks 26/27).

Cost binds to the decision it justified, not to a time bucket:

* FR-M45-01: every cost line is attributable to the gate decision (ledger
  sequence) and to the merged commit it justified — not only to an agent
  or a day.
* FR-M45-02: a change that merged reports its fully loaded cost *separated
  from abandoned attempts*; reconciling a sample of merged changes against
  the vendor-reported total reports unreconciled residue rather than
  absorbing it (AC-51).
* FR-M45-03: every figure carries its provenance from the closed
  vocabulary ``invoice_reconciled | vendor_api | locally_inferred |
  unknown``. The vocabulary is closed: anything else is a defect, not an
  extension point.
* FR-M45-04: figures of differing provenance are never summed into one
  displayed or exported number without the breakdown riding with it. The
  API enforces the shape: an aggregate IS a breakdown; there is no
  code path that returns a bare blended total.
* FR-M45-06 (the aggregation half): measured, estimated and unknown stay
  separate at every level of aggregation.

Zero model calls (FR-M36-07): arithmetic over ledger rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

PROVENANCE_CLASSES: tuple[str, ...] = (
    "invoice_reconciled",
    "vendor_api",
    "locally_inferred",
    "unknown",
)

MEASUREMENT_KINDS: tuple[str, ...] = ("measured", "estimated", "unknown")

OUTCOME_MERGED = "merged"
OUTCOME_ABANDONED = "abandoned"

#: Default residue tolerance for the AC-51 reconciliation (0.5% of the
#: vendor total). The tolerance is a stated constant, not a silent zero —
#: reconciliation always reports residue even when it is within tolerance.
DEFAULT_TOLERANCE = Decimal("0.005")


class ProvenanceError(ValueError):
    """A cost figure tried to carry a non-closed provenance class."""


@dataclass(frozen=True)
class CostLine:
    """One attributable unit of cost.

    ``gate_sequence`` binds the line to the gate decision that justified
    the spend (FR-M45-01); ``merged_commit`` binds it to the commit the
    change landed as. Both are ``None`` for spend that has not (yet) been
    bound — binding is evidence, and absence of evidence is recorded, not
    papered over.
    """

    story_id: str
    attempt_id: str
    actor_id: str
    phase: str
    cost_usd: Decimal
    provenance: str
    measurement: str = "unknown"
    gate_sequence: int | None = None
    merged_commit: str | None = None

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE_CLASSES:
            raise ProvenanceError(
                f"FR-M45-03: provenance must be one of {PROVENANCE_CLASSES},"
                f" got {self.provenance!r}"
            )
        if self.measurement not in MEASUREMENT_KINDS:
            raise ProvenanceError(
                f"FR-M45-06: measurement must be one of {MEASUREMENT_KINDS},"
                f" got {self.measurement!r}"
            )


@dataclass(frozen=True)
class Aggregation:
    """FR-M45-04: an aggregate IS a breakdown.

    ``by_provenance`` and ``by_measurement`` always ride with the total;
    serialising this value cannot drop them because there is no total
    field without the breakdown fields beside it.
    """

    by_provenance: Mapping[str, Decimal]
    by_measurement: Mapping[str, Decimal]
    total: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": str(self.total),
            "byProvenance": {k: str(v) for k, v in self.by_provenance.items()},
            "byMeasurement": {k: str(v) for k, v in self.by_measurement.items()},
        }


def aggregate(lines: Iterable[CostLine]) -> Aggregation:
    """Sum cost lines without ever blending provenance silently (FR-M45-04).

    The total is only ever returned together with its per-provenance and
    per-measurement breakdowns; callers displaying or exporting ``total``
    already hold the breakdown.
    """
    by_prov: dict[str, Decimal] = {p: Decimal("0") for p in PROVENANCE_CLASSES}
    by_meas: dict[str, Decimal] = {m: Decimal("0") for m in MEASUREMENT_KINDS}
    total = Decimal("0")
    for line in lines:
        by_prov[line.provenance] += line.cost_usd
        by_meas[line.measurement] += line.cost_usd
        total += line.cost_usd
    return Aggregation(
        by_provenance={k: v for k, v in by_prov.items() if v != 0},
        by_measurement={k: v for k, v in by_meas.items() if v != 0},
        total=total,
    )


@dataclass(frozen=True)
class ChangeCost:
    """FR-M45-02: the fully loaded cost of one change, split by outcome."""

    story_id: str
    merged_commit: str | None
    merged: Aggregation
    abandoned: Aggregation

    @property
    def fully_loaded(self) -> Aggregation:
        """Merged + abandoned, still carrying both breakdowns."""
        merged = self.merged
        abandoned = self.abandoned
        by_prov: dict[str, Decimal] = {
            p: merged.by_provenance.get(p, Decimal("0"))
            + abandoned.by_provenance.get(p, Decimal("0"))
            for p in PROVENANCE_CLASSES
        }
        by_meas: dict[str, Decimal] = {
            m: merged.by_measurement.get(m, Decimal("0"))
            + abandoned.by_measurement.get(m, Decimal("0"))
            for m in MEASUREMENT_KINDS
        }
        return Aggregation(
            by_provenance={k: v for k, v in by_prov.items() if v != 0},
            by_measurement={k: v for k, v in by_meas.items() if v != 0},
            total=merged.total + abandoned.total,
        )


def split_by_outcome(
    story_id: str,
    attempts: Sequence[CostLine],
    *,
    merged_commit: str | None,
) -> ChangeCost:
    """Separate the cost of the change that merged from abandoned attempts.

    An attempt counts toward *merged* only when it is bound to the merged
    commit (``attempt.merged_commit == merged_commit``); everything else on
    the story is abandoned-attempt cost. This keeps the separation honest
    under cherry-picking: only the attempt whose work actually landed is
    billed to the change.
    """
    merged_lines = [
        a for a in attempts if merged_commit is not None and a.merged_commit == merged_commit
    ]
    abandoned_lines = [a for a in attempts if a not in merged_lines]
    return ChangeCost(
        story_id=story_id,
        merged_commit=merged_commit,
        merged=aggregate(merged_lines),
        abandoned=aggregate(abandoned_lines),
    )


@dataclass(frozen=True)
class Reconciliation:
    """AC-51: reconcile a sample of merged changes against the vendor total.

    ``residue`` is reported, never absorbed: when the ledger sum and the
    vendor total differ, the difference is a named output, and
    ``within_tolerance`` is a statement about its size — not permission
    to drop it.
    """

    sample_size: int
    ledger_total: Decimal
    vendor_total: Decimal
    delta: Decimal
    residue: Decimal
    tolerance: Decimal
    within_tolerance: bool
    per_change: tuple[ChangeCost, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sampleSize": self.sample_size,
            "ledgerTotal": str(self.ledger_total),
            "vendorTotal": str(self.vendor_total),
            "delta": str(self.delta),
            "residue": str(self.residue),
            "tolerance": str(self.tolerance),
            "withinTolerance": self.within_tolerance,
            "perChange": [
                {
                    "storyId": c.story_id,
                    "mergedCommit": c.merged_commit,
                    "merged": c.merged.to_dict(),
                    "abandoned": c.abandoned.to_dict(),
                }
                for c in self.per_change
            ],
        }


def reconcile_sample(
    changes: Sequence[ChangeCost],
    *,
    vendor_total: Decimal,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> Reconciliation:
    """Reconcile merged-change costs to the vendor-reported total (AC-51).

    The ledger side counts each change's *merged* aggregation only —
    abandoned attempts are reported per change but never reconciled into
    the vendor figure, because the vendor bills attempts and the change
    bill is the merged work. The difference is ``residue``, reported
    regardless of size.
    """
    ledger_total = sum((c.merged.total for c in changes), Decimal("0"))
    delta = ledger_total - vendor_total
    residue = abs(delta)
    allowed = abs(vendor_total) * tolerance
    return Reconciliation(
        sample_size=len(changes),
        ledger_total=ledger_total,
        vendor_total=vendor_total,
        delta=delta,
        residue=residue,
        tolerance=tolerance,
        within_tolerance=residue <= allowed,
        per_change=tuple(changes),
    )


# -- ledger derivation -------------------------------------------------------


def _detail(ledger: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    if not row.get("input_ref"):
        return {}
    try:
        raw = ledger.read_blob(row["input_ref"], row["blob_key_id"])
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 — a unreadable detail is unknown, not fatal
        return {}


def lines_from_ledger(
    ledger: Any,
    *,
    story_ids: Sequence[str] | None = None,
    provenance: str = "locally_inferred",
) -> list[CostLine]:
    """Derive cost lines from ledger rows carrying ``cost_usd``.

    Provenance honesty (FR-M45-03): a bare ledger ``cost_usd`` was
    recorded by Meridian's own accounting, so it is ``locally_inferred``
    — never upgraded to ``vendor_api``. Callers reconciling against a
    billing feed re-derive lines from the feed and mark them
    ``invoice_reconciled``/``vendor_api`` themselves; this function refuses
    to mint that claim.
    """
    if provenance not in PROVENANCE_CLASSES:
        raise ProvenanceError(f"FR-M45-03: {provenance!r}")
    rows = ledger.query(action_type="tool_call", limit=100000)
    lines: list[CostLine] = []
    for row in rows:
        if story_ids is not None and row.get("story_id") not in story_ids:
            continue
        cost = row.get("cost_usd")
        if cost is None:
            continue
        detail = _detail(ledger, row)
        lines.append(
            CostLine(
                story_id=str(row.get("story_id") or "unknown"),
                attempt_id=str(row.get("run_id") or row.get("loop_id") or "attempt"),
                actor_id=str(row.get("actor_id") or "unknown"),
                phase=str(row.get("phase") or "unknown"),
                cost_usd=Decimal(str(cost)),
                provenance=provenance,
                measurement="measured",
                gate_sequence=detail.get("gateSequence"),
                merged_commit=detail.get("mergedCommit"),
            )
        )
    return lines


def bind_gate_and_commit(
    ledger: Any, lines: Sequence[CostLine], *, story_id: str
) -> list[CostLine]:
    """FR-M45-01: attach the gate decision and merged commit to a story's lines.

    The gate decision is the latest ``gate`` entry for the story whose
    decision is ``approved``; the merged commit is the ``headCommit`` in
    the story's most recent gate/ingest detail. Bindings that cannot be
    evidenced stay ``None`` — recorded as unbound, never guessed.
    """
    gate_rows = [
        row
        for row in ledger.query(action_type="gate", story_id=story_id, limit=1000)
        if row.get("decision") == "approved"
    ]
    gate_sequence = gate_rows[-1]["seq"] if gate_rows else None
    merged_commit: str | None = None
    for row in reversed(gate_rows):
        merged_commit = _detail(ledger, row).get("headCommit")
        if merged_commit:
            break
    return [
        CostLine(
            story_id=line.story_id,
            attempt_id=line.attempt_id,
            actor_id=line.actor_id,
            phase=line.phase,
            cost_usd=line.cost_usd,
            provenance=line.provenance,
            measurement=line.measurement,
            gate_sequence=gate_sequence,
            merged_commit=merged_commit,
        )
        for line in lines
    ]
