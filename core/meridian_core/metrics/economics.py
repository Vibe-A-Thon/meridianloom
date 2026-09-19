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

#: FR-M45-05: accepted-change economics extends beyond token spend. The
#: category vocabulary is closed for the same reason the provenance one
#: is: a free-text category is a different requirement wearing the same
#: name. New economics surface extends this tuple via a reviewed change.
COST_CATEGORIES: tuple[str, ...] = (
    "tokens",
    "provider_charge",
    "subscription",
    "compute",
    "storage",
    "failed_attempt",
    "human_review",
    "rework",
    "follow_up_fix",
)

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
    category: str = "tokens"
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
        if self.category not in COST_CATEGORIES:
            raise ProvenanceError(
                f"FR-M45-05: category must be one of {COST_CATEGORIES},"
                f" got {self.category!r}"
            )


@dataclass(frozen=True)
class Aggregation:
    """FR-M45-04: an aggregate IS a breakdown.

    ``by_provenance``, ``by_measurement`` and ``by_category`` always ride
    with the total; serialising this value cannot drop them because there
    is no total field without the breakdown fields beside it.
    """

    by_provenance: Mapping[str, Decimal]
    by_measurement: Mapping[str, Decimal]
    by_category: Mapping[str, Decimal]
    total: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": str(self.total),
            "byProvenance": {k: str(v) for k, v in self.by_provenance.items()},
            "byMeasurement": {k: str(v) for k, v in self.by_measurement.items()},
            "byCategory": {k: str(v) for k, v in self.by_category.items()},
        }


def aggregate(lines: Iterable[CostLine]) -> Aggregation:
    """Sum cost lines without ever blending provenance silently (FR-M45-04).

    The total is only ever returned together with its per-provenance,
    per-measurement and per-category breakdowns (FR-M45-05/06); callers
    displaying or exporting ``total`` already hold the breakdowns.
    """
    by_prov: dict[str, Decimal] = {p: Decimal("0") for p in PROVENANCE_CLASSES}
    by_meas: dict[str, Decimal] = {m: Decimal("0") for m in MEASUREMENT_KINDS}
    by_cat: dict[str, Decimal] = {c: Decimal("0") for c in COST_CATEGORIES}
    total = Decimal("0")
    for line in lines:
        by_prov[line.provenance] += line.cost_usd
        by_meas[line.measurement] += line.cost_usd
        by_cat[line.category] += line.cost_usd
        total += line.cost_usd
    return Aggregation(
        by_provenance={k: v for k, v in by_prov.items() if v != 0},
        by_measurement={k: v for k, v in by_meas.items() if v != 0},
        by_category={k: v for k, v in by_cat.items() if v != 0},
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
        by_cat: dict[str, Decimal] = {
            c: merged.by_category.get(c, Decimal("0"))
            + abandoned.by_category.get(c, Decimal("0"))
            for c in COST_CATEGORIES
        }
        return Aggregation(
            by_provenance={k: v for k, v in by_prov.items() if v != 0},
            by_measurement={k: v for k, v in by_meas.items() if v != 0},
            by_category={k: v for k, v in by_cat.items() if v != 0},
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
    rows = ledger.query_all(action_type="tool_call")
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
        for row in ledger.query_all(action_type="gate", story_id=story_id)
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


# -- FR-M45-06: sample vendor-bill reconciliation -----------------------------


@dataclass(frozen=True)
class BillLine:
    """One line of a vendor bill.

    ``category`` uses the same closed vocabulary as cost lines; an
    excluded line names its exclusion reason rather than vanishing — the
    requirement says every excluded charge category is documented.
    """

    category: str
    amount_usd: Decimal
    provenance: str = "invoice_reconciled"
    excluded_reason: str | None = None

    def __post_init__(self) -> None:
        if self.category not in COST_CATEGORIES:
            raise ProvenanceError(
                f"FR-M45-05: bill category must be one of {COST_CATEGORIES},"
                f" got {self.category!r}"
            )
        if self.provenance != "invoice_reconciled":
            raise ProvenanceError(
                "FR-M45-03: a bill line is vendor-invoice evidence; its"
                f" provenance is invoice_reconciled, got {self.provenance!r}"
            )


@dataclass(frozen=True)
class BillReconciliation:
    """FR-M45-06: reconcile a sample bill to the ledger-side figure.

    ``within_tolerance`` is only meaningful when ``detailed_billing`` is
    true — where the bill lacks line detail the reconciliation says so
    (``reconciled: False``) rather than comparing a total against a guess.
    Excluded categories are named with their reasons, never absorbed.
    """

    reconciled: bool
    detailed_billing: bool
    bill_total: Decimal
    included_total: Decimal
    ledger_total: Decimal
    residue: Decimal
    tolerance: Decimal
    within_tolerance: bool | None
    exclusions: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reconciled": self.reconciled,
            "detailedBilling": self.detailed_billing,
            "billTotal": str(self.bill_total),
            "includedTotal": str(self.included_total),
            "ledgerTotal": str(self.ledger_total),
            "residue": str(self.residue),
            "tolerance": str(self.tolerance),
            "withinTolerance": self.within_tolerance,
            "exclusions": dict(self.exclusions),
        }


def reconcile_bill(
    bill_lines: Sequence[BillLine],
    *,
    ledger_total: Decimal,
    detailed_billing: bool,
    tolerance: Decimal = Decimal("0.01"),
) -> BillReconciliation:
    """Reconcile a sample vendor bill against the ledger (FR-M45-06).

    Where detailed billing permits (``detailed_billing=True``) the included
    lines must reconcile within 1%. Where it does not, the reconciliation
    is reported as not run (``reconciled: False``, ``within_tolerance:
    None``) — an unmeasurable condition is stated, never passed off.
    Excluded lines are documented by category with their reason.
    """
    bill_total = sum((b.amount_usd for b in bill_lines), Decimal("0"))
    included = [b for b in bill_lines if b.excluded_reason is None]
    included_total = sum((b.amount_usd for b in included), Decimal("0"))
    exclusions = {
        b.category: b.excluded_reason or ""
        for b in bill_lines
        if b.excluded_reason is not None
    }
    if not detailed_billing:
        return BillReconciliation(
            reconciled=False,
            detailed_billing=False,
            bill_total=bill_total,
            included_total=included_total,
            ledger_total=ledger_total,
            residue=abs(included_total - ledger_total),
            tolerance=tolerance,
            within_tolerance=None,
            exclusions=exclusions,
        )
    residue = abs(included_total - ledger_total)
    return BillReconciliation(
        reconciled=True,
        detailed_billing=True,
        bill_total=bill_total,
        included_total=included_total,
        ledger_total=ledger_total,
        residue=residue,
        tolerance=tolerance,
        within_tolerance=residue <= (abs(included_total) * tolerance),
        exclusions=exclusions,
    )


# -- FR-M45-07: hosted budgets stop, unhosted warns (unenforced) ---------------


@dataclass(frozen=True)
class BudgetPolicy:
    """A configured spend ceiling and whether Meridian can enforce it.

    ``hosted`` is true when Meridian schedules the agent's work — only
    then can scheduling stop before the ceiling. An unhosted agent runs
    outside Meridian's control, so the same check produces a warning
    explicitly labelled unenforced, never a stop.
    """

    ceiling_usd: Decimal
    hosted: bool
    currency: str = "USD"


@dataclass(frozen=True)
class BudgetDecision:
    """``stop`` is enforceable only when ``hosted``; otherwise the decision
    is an advisory warning whose ``enforced`` flag is False and says so in
    ``label`` — a configuration tier switch is not a paid entitlement and
    an advisory must never present as a gate."""

    allowed: bool
    hosted: bool
    enforced: bool
    label: str
    spend_to_date_usd: Decimal
    projected_next_usd: Decimal
    ceiling_usd: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "hosted": self.hosted,
            "enforced": self.enforced,
            "label": self.label,
            "spendToDateUsd": str(self.spend_to_date_usd),
            "projectedNextUsd": str(self.projected_next_usd),
            "ceilingUsd": str(self.ceiling_usd),
        }


def check_budget(
    policy: BudgetPolicy, *, spend_to_date_usd: Decimal, projected_next_usd: Decimal
) -> BudgetDecision:
    """FR-M45-07: stop hosted scheduling before the ceiling; warn unhosted.

    Hosted: the next unit of work is refused when spend-to-date plus its
    projection would reach the ceiling — the stop happens BEFORE the
    ceiling is crossed. Unhosted: an advisory warning, explicitly labelled
    unenforced, because Meridian cannot stop work it does not schedule.
    """
    would_reach = (spend_to_date_usd + projected_next_usd) >= policy.ceiling_usd
    if policy.hosted:
        return BudgetDecision(
            allowed=not would_reach,
            hosted=True,
            enforced=True,
            label="enforced: hosted scheduling stops before the ceiling",
            spend_to_date_usd=spend_to_date_usd,
            projected_next_usd=projected_next_usd,
            ceiling_usd=policy.ceiling_usd,
        )
    return BudgetDecision(
        allowed=True,  # advisory only — unhosted work is not ours to stop
        hosted=False,
        enforced=False,
        label=(
            "unenforced advisory: Meridian does not schedule this agent;"
            " the ceiling cannot be enforced from here"
        ),
        spend_to_date_usd=spend_to_date_usd,
        projected_next_usd=projected_next_usd,
        ceiling_usd=policy.ceiling_usd,
    )
