"""FR-M13-01…05, 07 (F3 remaining): decision records with structurally
labelled unverified rationale, calibration tracking, ablation replay
marked as evidence and mandatory for high blast-radius gates, and the
absolute rule that no gate passes on an explanation.
"""

from __future__ import annotations

import pytest

from meridian_core.decisions import (
    UNVERIFIED_NARRATIVE_LABEL,
    AblationRunner,
    CalibrationTracker,
    DecisionRecord,
    ExplanationGateError,
    GateInputs,
    Rationale,
    evaluate_gate,
)


def record(decision_id="d1", agent="agent-1", confidence=0.9, **inputs):
    return DecisionRecord(
        decision_id=decision_id,
        agent_id=agent,
        inputs=inputs or {"a": 1, "b": 2, "noise": "x"},
        retrieved_memory=("mem-1",),
        tool_calls=("tool_call",),
        output={"answer": 42},
        confidence=confidence,
        rationale=Rationale("I chose 42 because it felt right"),
    )


# -- FR-M13-01/02: record + labelled rationale ----------------------------------


def test_record_carries_full_provenance() -> None:
    rec = record()
    as_dict = rec.to_dict()
    assert as_dict["inputs"] == {"a": 1, "b": 2, "noise": "x"}
    assert as_dict["retrievedMemory"] == ["mem-1"]
    assert as_dict["toolCalls"] == ["tool_call"]
    assert as_dict["confidence"] == 0.9


def test_rationale_only_renders_labelled() -> None:
    rec = record()
    rendered = rec.to_dict()["rationale"]
    assert rendered.startswith(f"[{UNVERIFIED_NARRATIVE_LABEL}]")
    assert "felt right" in rendered
    # The raw text is not exposed by the public shape.
    assert UNVERIFIED_NARRATIVE_LABEL in rendered


# -- FR-M13-03: calibration -------------------------------------------------------


def test_calibration_tracked_over_time() -> None:
    tracker = CalibrationTracker()
    for i in range(6):
        rec = record(decision_id=f"d{i}", confidence=0.8)
        tracker.capture(rec)
        tracker.record_outcome(f"d{i}", 1.0)  # agent over-claimed by 0.2
    cal = tracker.calibration("agent-1")
    assert cal.samples == 6
    assert cal.mean_calibration_error == pytest.approx(0.2)
    alongside = cal.alongside(0.95)
    assert alongside["historicalCalibrationError"] == pytest.approx(0.2)
    assert alongside["claimedConfidence"] == 0.95


def test_calibration_insufficient_evidence_is_none() -> None:
    tracker = CalibrationTracker()
    tracker.capture(record(decision_id="d0"))
    tracker.record_outcome("d0", 1.0)
    cal = tracker.calibration("agent-1")
    assert cal.mean_calibration_error is None
    assert "insufficient evidence" in cal.alongside(0.9)["note"]


# -- FR-M13-04: ablation replay ------------------------------------------------------


def test_ablation_marks_result_as_evidence_and_detects_change() -> None:
    def decide(inputs):
        return {"answer": inputs.get("a", 0) + inputs.get("b", 0)}

    rec = DecisionRecord(
        decision_id="d1", agent_id="a", inputs={"a": 1, "b": 2, "noise": "x"},
        retrieved_memory=(), tool_calls=(), output={"answer": 3},
        confidence=0.9,
    )
    runner = AblationRunner(decide)
    result = runner.ablate(rec, "noise")
    assert result.output_changed is False  # noise carried no weight
    assert "evidence" in result.labelled()
    result_b = runner.ablate(rec, "b")
    assert result_b.output_changed is True
    assert result_b.output == {"answer": 1}


# -- FR-M13-05/07: gates ---------------------------------------------------------------


def _gate(**overrides):
    base = dict(
        tests_passed=True,
        scans_passed=True,
        approvals=("human-lead",),
        change_class="ordinary",
        ablations=(),
    )
    base.update(overrides)
    return GateInputs(**base)


def test_high_blast_radius_requires_ablation() -> None:
    assert evaluate_gate(_gate()) is True
    assert (
        evaluate_gate(_gate(change_class="security_relevant_change")) is False
    )
    runner = AblationRunner(lambda inputs: inputs)
    rec = record()
    ablation = runner.ablate(rec, "noise")
    assert (
        evaluate_gate(
            _gate(change_class="schema_migration", ablations=(ablation,))
        )
        is True
    )


def test_gate_refuses_explanations_loudly() -> None:
    with pytest.raises(ExplanationGateError, match="FR-M13-07"):
        evaluate_gate(_gate(), rationale=Rationale("trust me"))
