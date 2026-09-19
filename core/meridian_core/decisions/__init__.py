"""M13 Decision Records — FR-M13-01…05, 07.

FR-M13-01: every consequential agent decision produces a decision record:
inputs, retrieved memory, tool calls, output, stated confidence.

FR-M13-02: self-reported rationale is stored and carried EXPLICITLY
LABELLED as unverified narrative. The label is structural — a
``Rationale`` is a distinct type whose only renderable form carries the
label; there is no code path that exposes the raw text without it.

FR-M13-03: confidence is recorded at capture and calibration is tracked
over time (|claimed − observed|), so any current confidence claim can be
shown next to the agent's historical calibration error.

FR-M13-04: ablation replay re-runs a decision with one input factor
removed; the result is marked as EVIDENCE (contrast to narrative).
FR-M13-05: ablation is mandatory before a gate for high blast-radius
classes (schema migration, public API contract change, security-relevant,
cross-service) — the gate refuses to evaluate without it.

FR-M13-07: no gate passes on the basis of an explanation. Gates consume
tests, scans, and approvals only; a rationale — verified or not — can
never satisfy a gate criterion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

UNVERIFIED_NARRATIVE_LABEL = "unverified narrative — not independently checked"
EVIDENCE_LABEL = "evidence — produced by controlled replay"

HIGH_BLAST_RADIUS_CLASSES = (
    "schema_migration",
    "public_api_contract_change",
    "security_relevant_change",
    "cross_service_change",
)


@dataclass(frozen=True)
class Rationale:
    """FR-M13-02: self-reported rationale. The ONLY way to read it is
    labelled — ``text`` is private by convention and every consumer goes
    through :meth:`labelled`."""

    _text: str

    def labelled(self) -> str:
        return f"[{UNVERIFIED_NARRATIVE_LABEL}] {self._text}"


@dataclass(frozen=True)
class DecisionRecord:
    """FR-M13-01: one consequential decision."""

    decision_id: str
    agent_id: str
    inputs: Mapping[str, Any]
    retrieved_memory: tuple[str, ...]
    tool_calls: tuple[str, ...]
    output: Any
    confidence: float  # claimed at capture (FR-M13-03)
    rationale: Rationale | None = None
    observed_outcome: float | None = None  # filled later; 0/1 or score

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "agentId": self.agent_id,
            "inputs": dict(self.inputs),
            "retrievedMemory": list(self.retrieved_memory),
            "toolCalls": list(self.tool_calls),
            "output": self.output,
            "confidence": self.confidence,
            "rationale": self.rationale.labelled() if self.rationale else None,
            "observedOutcome": self.observed_outcome,
        }


@dataclass(frozen=True)
class Calibration:
    """FR-M13-03: historical calibration error beside any claim."""

    agent_id: str
    samples: int
    mean_calibration_error: float | None

    def alongside(self, claim: float) -> Mapping[str, Any]:
        return {
            "claimedConfidence": claim,
            "historicalCalibrationError": self.mean_calibration_error,
            "samples": self.samples,
            "note": (
                "insufficient evidence — calibrate before trusting the claim"
                if self.samples < 5 or self.mean_calibration_error is None
                else "calibration error is the mean |claimed − observed|"
            ),
        }


class CalibrationTracker:
    """Records outcomes and derives calibration error per agent."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []

    def capture(self, record: DecisionRecord) -> None:
        self._records.append(record)

    def record_outcome(self, decision_id: str, observed: float) -> None:
        for index, record in enumerate(self._records):
            if record.decision_id == decision_id:
                self._records[index] = DecisionRecord(
                    decision_id=record.decision_id,
                    agent_id=record.agent_id,
                    inputs=record.inputs,
                    retrieved_memory=record.retrieved_memory,
                    tool_calls=record.tool_calls,
                    output=record.output,
                    confidence=record.confidence,
                    rationale=record.rationale,
                    observed_outcome=observed,
                )
                return
        raise KeyError(decision_id)

    def calibration(self, agent_id: str) -> Calibration:
        observed = [
            r for r in self._records
            if r.agent_id == agent_id and r.observed_outcome is not None
        ]
        if len(observed) < 5:
            return Calibration(agent_id, len(observed), None)
        errors = [abs(r.confidence - (r.observed_outcome or 0.0)) for r in observed]
        return Calibration(
            agent_id, len(observed), round(sum(errors) / len(errors), 4)
        )


@dataclass(frozen=True)
class AblationResult:
    """FR-M13-04: a replay with one factor removed, marked as evidence."""

    decision_id: str
    removed_factor: str
    output: Any
    output_changed: bool

    def labelled(self) -> str:
        return f"[{EVIDENCE_LABEL}] factor={self.removed_factor}"


class AblationRunner:
    """Re-runs decisions with a factor removed. The decision function is
    the caller's (deterministic engine or recorded model call replay);
    this runner owns the marking and the mandatory-before-gate rule."""

    def __init__(self, decide: Callable[[Mapping[str, Any]], Any]) -> None:
        self._decide = decide

    def ablate(
        self, record: DecisionRecord, factor: str
    ) -> AblationResult:
        if factor not in record.inputs:
            raise KeyError(f"factor {factor!r} not in decision inputs")
        modified = {k: v for k, v in record.inputs.items() if k != factor}
        output = self._decide(modified)
        return AblationResult(
            decision_id=record.decision_id,
            removed_factor=factor,
            output=output,
            output_changed=output != record.output,
        )


@dataclass(frozen=True)
class GateInputs:
    """What a gate may consume (FR-M13-07). Explanations are not here."""

    tests_passed: bool
    scans_passed: bool
    approvals: tuple[str, ...]
    change_class: str
    ablations: tuple[AblationResult, ...] = ()


class ExplanationGateError(ValueError):
    """FR-M13-07: an attempt to satisfy a gate with an explanation."""


def evaluate_gate(gate: GateInputs, *, rationale: Rationale | None = None) -> bool:
    """FR-M13-05/07: gates evaluate tests, scans, approvals — and for
    high blast-radius classes, mandatory ablation. A rationale argument
    is REFUSED, not ignored: passing it is a programming error, so the
    temptation to gate on explanation fails loudly at the boundary."""
    if rationale is not None:
        raise ExplanationGateError(
            "FR-M13-07: no gate is passable on the basis of an explanation;"
            " remove the rationale from the gate inputs"
        )
    satisfied = gate.tests_passed and gate.scans_passed and bool(gate.approvals)
    if not satisfied:
        return False
    if gate.change_class in HIGH_BLAST_RADIUS_CLASSES:
        # FR-M13-05: ablation replay is mandatory before the gate.
        return bool(gate.ablations) and all(
            isinstance(a, AblationResult) for a in gate.ablations
        )
    return True
