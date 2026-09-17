"""FR-M45-01…04, AMD-M39, AC-51 (N2 Workstream F tasks 26/27): cost binds to
the gate decision and the merged commit; merged cost is separated from
abandoned attempts; a 20-change sample reconciles to the vendor total with
residue reported; provenance classes never blend without a breakdown.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import economics as eco


def line(story="STORY-1", attempt="run-1", cost="10.00", provenance="locally_inferred",
       measurement="measured", gate=None, commit=None):
    return eco.CostLine(
        story_id=story,
        attempt_id=attempt,
        actor_id="agent-1",
        phase="build",
        cost_usd=Decimal(cost),
        provenance=provenance,
        measurement=measurement,
        gate_sequence=gate,
        merged_commit=commit,
    )


# -- closed vocabulary --------------------------------------------------------


def test_provenance_vocabulary_is_closed() -> None:
    assert eco.PROVENANCE_CLASSES == (
        "invoice_reconciled",
        "vendor_api",
        "locally_inferred",
        "unknown",
    )
    with pytest.raises(eco.ProvenanceError, match="FR-M45-03"):
        line(provenance="guessed")
    with pytest.raises(eco.ProvenanceError, match="FR-M45-06"):
        line(measurement="precise-ish")


# -- FR-M45-04: no blended number without its breakdown ------------------------


def test_aggregate_total_always_rides_with_breakdown() -> None:
    agg = eco.aggregate(
        [
            line(cost="10.00", provenance="vendor_api"),
            line(cost="5.00", provenance="invoice_reconciled"),
            line(cost="2.50", provenance="locally_inferred"),
        ]
    )
    as_dict = agg.to_dict()
    # The serialised form cannot drop the breakdown: total exists only
    # beside byProvenance/byMeasurement.
    assert set(as_dict) == {"total", "byProvenance", "byMeasurement"}
    assert as_dict["total"] == "17.50"
    assert as_dict["byProvenance"] == {
        "vendor_api": "10.00",
        "invoice_reconciled": "5.00",
        "locally_inferred": "2.50",
    }


def test_measurement_classes_stay_separate_in_aggregation() -> None:
    agg = eco.aggregate(
        [line(cost="3.00", measurement="measured"), line(cost="1.00", measurement="estimated")]
    )
    assert agg.by_measurement == {"measured": Decimal("3.00"), "estimated": Decimal("1.00")}


# -- FR-M45-02: merged vs abandoned --------------------------------------------


def test_merged_cost_separated_from_abandoned_attempts() -> None:
    attempts = [
        line(attempt="run-1", cost="40.00", commit="abc"),  # landed
        line(attempt="run-2", cost="25.00", commit=None),  # abandoned
        line(attempt="run-3", cost="15.00", commit="deadbeef"),  # superseded
    ]
    change = eco.split_by_outcome("STORY-1", attempts, merged_commit="abc")
    assert change.merged.total == Decimal("40.00")
    assert change.abandoned.total == Decimal("40.00")
    assert change.fully_loaded.total == Decimal("80.00")


def test_unbound_change_counts_all_as_abandoned() -> None:
    change = eco.split_by_outcome(
        "STORY-2", [line(story="STORY-2", cost="9.00")], merged_commit=None
    )
    assert change.merged.total == Decimal("0")
    assert change.abandoned.total == Decimal("9.00")


# -- AC-51: 20-change reconciliation with residue --------------------------------


def twenty_changes(residue_line: Decimal | None = None):
    changes = []
    for i in range(20):
        cost = Decimal("100.00")
        if residue_line is not None and i == 0:
            cost = cost + residue_line
        changes.append(
            eco.split_by_outcome(
                f"STORY-{i}",
                [line(story=f"STORY-{i}", cost=str(cost), commit=f"c{i}")],
                merged_commit=f"c{i}",
            )
        )
    return changes


def test_twenty_merged_changes_reconcile_within_tolerance() -> None:
    changes = twenty_changes()
    vendor = Decimal("2000.00")
    recon = eco.reconcile_sample(changes, vendor_total=vendor)
    assert recon.sample_size == 20
    assert recon.ledger_total == Decimal("2000.00")
    assert recon.residue == Decimal("0")
    assert recon.within_tolerance is True


def test_residue_is_reported_not_absorbed() -> None:
    changes = twenty_changes(residue_line=Decimal("25.00"))
    vendor = Decimal("2000.00")
    recon = eco.reconcile_sample(changes, vendor_total=vendor)
    assert recon.ledger_total == Decimal("2025.00")
    assert recon.delta == Decimal("25.00")
    assert recon.residue == Decimal("25.00")
    assert recon.within_tolerance is False  # 25.00 > 0.5% of 2000 = 10.00
    # Per-change breakdown survived into the report.
    assert recon.to_dict()["perChange"][0]["merged"]["total"] == "125.00"


def test_residue_within_tolerance_is_still_reported() -> None:
    # 7.50 is inside the 0.5% band (<= 10.00): within_tolerance, but the
    # residue must still be a named output — tolerance is a statement about
    # size, not permission to drop the difference.
    changes = twenty_changes(residue_line=Decimal("7.50"))
    recon = eco.reconcile_sample(changes, vendor_total=Decimal("2000.00"))
    assert recon.within_tolerance is True
    assert recon.residue == Decimal("7.50")


def test_abandoned_cost_never_reconciled_into_vendor_figure() -> None:
    attempts = [line(cost="50.00", commit="c1"), line(cost="30.00", commit=None)]
    change = eco.split_by_outcome("S", attempts, merged_commit="c1")
    recon = eco.reconcile_sample([change], vendor_total=Decimal("50.00"))
    assert recon.ledger_total == Decimal("50.00")
    assert recon.residue == Decimal("0")
    # ...while the abandoned 30.00 remains visible in the per-change report.
    assert recon.to_dict()["perChange"][0]["abandoned"]["total"] == "30.00"


# -- FR-M45-01: ledger binding ---------------------------------------------------


def _seed_ledger(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    ledger.append(
        {
            "story_id": "S1",
            "phase": "build",
            "loop_id": "L1",
            "loop_iteration": 1,
            "actor_id": "agent-1",
            "actor_version": "0.0.1",
            "actor_kind": "role",
            "policy_version": "policy-v1",
            "action_type": "tool_call",
            "cost_usd": 12.5,
            "run_id": "run-9",
        }
    )
    ledger.append(
        {
            "story_id": "S1",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0.0.1",
            "actor_kind": "meta",
            "policy_version": "policy-v1",
            "action_type": "gate",
            "decision": "approved",
        },
    )
    return ledger


def test_lines_from_ledger_default_to_locally_inferred(tmp_path) -> None:
    ledger = _seed_ledger(tmp_path)
    try:
        lines = eco.lines_from_ledger(ledger)
        assert len(lines) == 1
        assert lines[0].cost_usd == Decimal("12.5")
        assert lines[0].provenance == "locally_inferred"
        assert lines[0].attempt_id == "run-9"
        # The ledger's own accounting must never be minted as vendor truth.
        with pytest.raises(eco.ProvenanceError):
            eco.lines_from_ledger(ledger, provenance="vendor_api_minted")
    finally:
        ledger.close()


def test_bind_gate_and_commit_attaches_decision(tmp_path) -> None:
    ledger = _seed_ledger(tmp_path)
    try:
        # give the gate entry a headCommit detail
        row = ledger.query(action_type="gate", story_id="S1")[0]
        # re-read detail path: bind uses _detail on gate rows; append a gate
        # entry whose blob carries headCommit via input
        ledger.append(
            {
                "story_id": "S1",
                "phase": "review",
                "loop_id": "governance",
                "loop_iteration": 2,
                "actor_id": "governor",
                "actor_version": "0.0.1",
                "actor_kind": "meta",
                "policy_version": "policy-v1",
                "action_type": "gate",
                "decision": "approved",
                "input": '{"headCommit": "cafe"}',
            }
        )
        del row
        lines = eco.lines_from_ledger(ledger)
        bound = eco.bind_gate_and_commit(ledger, lines, story_id="S1")
        assert bound[0].gate_sequence is not None
        assert bound[0].merged_commit == "cafe"
    finally:
        ledger.close()
