"""The policy simulator (FR-M42-15) — N2 Workstream C task T12.

A proposed policy-pack change replays against the historical gate and
permission verdicts; the report is a verdict-by-verdict diff naming which
decisions the change would have altered. Deterministic, read-only (the
ledger sequence never moves), honest about inputs it does not have (P26).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core.governance import policy_simulator
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider

PACK_ORIGINAL = """
version: 2
profiles:
  verify:
    description: verification
    criteria:
      - id: tests-pass
        kind: testEvidence
"""

PACK_STRICT = """
version: 3
profiles:
  verify:
    description: verification plus human approval
    criteria:
      - id: tests-pass
        kind: testEvidence
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
"""

PACK_BROKEN = "version: [not-a-mapping\n"

PACK_ACP_ORIGINAL = """
version: 2
acpPermissions:
  adapters:
    '*':
      probation: [read, search]
      active: [read, search, edit, execute]
    gemini:
      probation: [read]
      active: [read, edit, execute]
"""

PACK_ACP_TIGHTENED = """
version: 3
acpPermissions:
  adapters:
    '*':
      probation: [read, search]
      active: [read, search, edit]
    gemini:
      probation: [read]
      active: [read, edit]
      deny: [execute]
"""

PACK_ACP_UNCHANGED = PACK_ACP_ORIGINAL

PACK_ACP_RELAXED = """
version: 3
acpPermissions:
  adapters:
    '*':
      probation: [read, search]
      active: [read, search, edit, execute]
    gemini:
      probation: [read, execute]
      active: [read, edit, execute]
"""

PACK_COMBINED = """
version: 3
profiles:
  verify:
    description: verification plus human approval
    criteria:
      - id: tests-pass
        kind: testEvidence
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
acpPermissions:
  adapters:
    '*':
      probation: [read, search]
      active: [read, search, edit]
    gemini:
      probation: [read]
      active: [read, edit]
      deny: [execute]
"""

#: A packet that passes the ORIGINAL verify profile (passing tests, no
#: approvals) and would be REJECTED by the strict profile (no lead).
PACKET_NO_APPROVAL = {
    "storyId": "story-7",
    "branch": "feature/story-7",
    "evidence": [{"kind": "test", "status": "passed"}],
}


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _append(ledger: Ledger, *, action_type: str, decision: str, detail: dict) -> int:
    return ledger.append(
        {
            "story_id": detail.get("storyId", "story-7"),
            "phase": "review" if action_type == "gate" else "build",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/original",
            "action_type": action_type,
            "decision": decision,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(detail, ensure_ascii=False),
        }
    ).sequence


def _gate_verdicts(ledger: Ledger) -> list[dict]:
    return ledger.query(action_type="gate", limit=1000)


# -- gate verdict replay ---------------------------------------------------------


def test_simulation_reports_changed_gate_verdicts(ledger: Ledger) -> None:
    """FR-M42-15: adding a humanApproval criterion to the verify profile
    would have reversed the historical approved verdicts that lacked a
    lead approval — the diff names each one."""
    seq = _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_STRICT)
    assert report.proposed_errors == ()
    assert len(report.verdicts) == 1
    diff = report.verdicts[0]
    assert diff.sequence == seq
    assert diff.action_type == "gate"
    assert diff.original == "approved"
    assert diff.simulated == "rejected"
    assert diff.changed
    assert "lead" in diff.reason
    assert report.changed == [diff]


def test_simulation_reports_no_change_when_verdicts_hold(ledger: Ledger) -> None:
    """FR-M42-15: a proposal that reaches the same verdicts reports them
    unchanged — the simulator explains silence too."""
    _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_ORIGINAL)
    assert len(report.verdicts) == 1
    assert not report.verdicts[0].changed
    assert report.verdicts[0].simulated == "approved"


def test_simulation_fail_closed_proposal_blocks_every_verdict(ledger: Ledger) -> None:
    """FR-M42-15 + SEC-35 honesty: a malformed proposal replays as
    rejected everywhere, with the parse errors reported — activating a
    broken pack is visible before it happens."""
    _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_BROKEN)
    assert report.proposed_errors
    assert len(report.changed) == 1
    diff = report.changed[0]
    assert diff.simulated == "rejected"
    assert "fails closed" in diff.reason


def test_simulation_gate_inputs_missing_reported_not_fabricated(ledger: Ledger) -> None:
    """P26: a gate row recorded without its packet/profile cannot be
    replayed — the diff says unknown, changed False; it never invents a
    verdict."""
    seq = _append(ledger, action_type="gate", decision="approved", detail={"gate": "verify"})
    report = policy_simulator.simulate_policy_change(ledger, PACK_STRICT)
    assert len(report.verdicts) == 1
    diff = report.verdicts[0]
    assert diff.sequence == seq
    assert diff.simulated == "unknown"
    assert not diff.changed


# -- permission decision replay ---------------------------------------------------


def test_simulation_reports_changed_permission_decisions(ledger: Ledger) -> None:
    """FR-M42-15: tightening the allow-list would have denied historical
    grants the policy gate previously let reach the human."""
    seq = _append(
        ledger,
        action_type="permission_decision",
        decision="approved",
        detail={
            "sessionId": "s1",
            "adapterId": "gemini",
            "toolKind": "execute",
            "adapterState": "active",
        },
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_ACP_TIGHTENED)
    diffs = [d for d in report.verdicts if d.action_type == "permission_decision"]
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.sequence == seq
    assert diff.original == "approved"
    assert diff.simulated == "rejected"  # execute is denied in the proposal
    assert diff.changed
    assert "deny" in diff.reason


def test_simulation_permission_deny_lifted_by_proposal(ledger: Ledger) -> None:
    """The reverse direction: a proposal that grants a previously denied
    kind flips the historical rejection to an approval."""
    _append(
        ledger,
        action_type="permission_decision",
        decision="rejected",
        detail={
            "sessionId": "s1",
            "adapterId": "gemini",
            "toolKind": "execute",
            "adapterState": "probation",
            "reason": "execute is not in the probation allow-list",
        },
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_ACP_RELAXED)
    diff = report.changed[0]
    assert diff.original == "rejected"
    assert diff.simulated == "approved"
    assert diff.changed


def test_simulation_permission_inputs_missing_reported(ledger: Ledger) -> None:
    """Permission rows recorded without adapterState (the pre-simulator
    recording shape) replay as unknown, never fabricated (P26)."""
    seq = _append(
        ledger,
        action_type="permission_decision",
        decision="approved",
        detail={"sessionId": "s1", "adapterId": "gemini", "toolKind": "execute"},
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_ACP_TIGHTENED)
    diff = next(d for d in report.verdicts if d.sequence == seq)
    assert diff.simulated == "unknown"
    assert not diff.changed
    assert "inputs not recorded" in diff.reason


# -- properties: read-only, deterministic, sliced ---------------------------------


def test_simulation_never_writes_to_the_ledger(ledger: Ledger) -> None:
    """FR-M42-15: the simulator is an explanation, never a mutation — the
    ledger sequence is identical before and after a simulation."""
    _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    before = ledger.last_sequence
    policy_simulator.simulate_policy_change(ledger, PACK_COMBINED)
    assert ledger.last_sequence == before
    assert _gate_verdicts(ledger)[0]["decision"] == "approved"  # untouched


def test_simulation_is_deterministic(ledger: Ledger) -> None:
    """Same slice, same proposal: identical reports, run twice."""
    _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    _append(
        ledger,
        action_type="permission_decision",
        decision="approved",
        detail={
            "sessionId": "s1",
            "adapterId": "gemini",
            "toolKind": "execute",
            "adapterState": "active",
        },
    )
    first = policy_simulator.simulate_policy_change(ledger, PACK_COMBINED)
    second = policy_simulator.simulate_policy_change(ledger, PACK_COMBINED)
    assert first.to_dict() == second.to_dict()


def test_simulation_honours_the_sequence_slice(ledger: Ledger) -> None:
    """The historical slice bounds the replay population: verdicts outside
    [from_sequence, to_sequence] are not examined."""
    first = _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    second = _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    report = policy_simulator.simulate_policy_change(
        ledger, PACK_STRICT, from_sequence=second, to_sequence=second
    )
    assert [d.sequence for d in report.verdicts] == [second]
    assert first not in [d.sequence for d in report.verdicts]


def test_simulation_combined_pack_replays_both_populations(ledger: Ledger) -> None:
    """One proposal touching gates AND the allow-list diffs both verdict
    populations in a single report."""
    gate_seq = _append(
        ledger,
        action_type="gate",
        decision="approved",
        detail={"method": "gate.evaluate", "gate": "verify", "packet": PACKET_NO_APPROVAL},
    )
    perm_seq = _append(
        ledger,
        action_type="permission_decision",
        decision="approved",
        detail={
            "sessionId": "s1",
            "adapterId": "gemini",
            "toolKind": "execute",
            "adapterState": "active",
        },
    )
    report = policy_simulator.simulate_policy_change(ledger, PACK_COMBINED)
    assert {d.sequence for d in report.changed} == {gate_seq, perm_seq}
    assert report.to_dict()["changedCount"] == 2
