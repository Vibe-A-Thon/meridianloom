"""FR-M42-15 (FUT-015; N2 Workstream C task T12): the policy simulator.

Given a PROPOSED policy-pack change (the pack's YAML text, exactly what a
policy author would activate), replay it against a historical ledger
slice and report WHICH historical verdicts the change would have altered
— verdict by verdict, deterministically, BEFORE the change is activated.

Two verdict populations replay:

* **gate decisions** — historical ``gate`` entries carry their full
  evaluation inputs (the packet and the profile name, recorded by
  ``gate.evaluate``); each is re-evaluated with the proposed pack through
  the same :func:`governance.engine.evaluate` the live path uses. A
  fail-closed proposed pack replays as ``rejected`` for every verdict
  (its errors ride the diff's reason) — the honest effect of activating
  a malformed pack.
* **permission decisions** — historical ``permission_decision`` entries
  replay against the proposed pack's ``acpPermissions`` allow-list: for
  the recorded ``adapterId`` and ``adapterState``, is the recorded
  ``toolKind`` still grantable? Entries recorded without those inputs
  cannot be replayed honestly: they are reported with
  ``simulated: "unknown"`` and ``changed: False`` — a simulator NEVER
  fabricates a verdict from inputs it does not have (P26).

The simulator is read-only: it never appends to the ledger (a test pins
the sequence counter across a simulation). It is deterministic: pure
re-evaluation over recorded rows — same slice, same proposal, same diff.

Zero model calls (FR-M36-07): predicate evaluation only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..ledger.core import Ledger
from . import engine as governance_engine
from .policy import PolicyPack, parse_policy_pack

__all__ = [
    "GATE_ACTION",
    "PERMISSION_ACTION",
    "SimulationReport",
    "VerdictDiff",
    "simulate_policy_change",
]

#: The historical verdict populations the simulator replays.
GATE_ACTION = "gate"
PERMISSION_ACTION = "permission_decision"

_SIMULATED_ACTIONS = (GATE_ACTION, PERMISSION_ACTION)


@dataclass(frozen=True)
class VerdictDiff:
    """One historical verdict, replayed: what was recorded, what the
    proposed pack would have decided, and whether that differs."""

    sequence: int
    action_type: str  # gate | permission_decision
    story_id: str
    original: str  # the recorded decision
    simulated: str  # the proposed pack's verdict ("unknown" = inputs missing)
    changed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "actionType": self.action_type,
            "storyId": self.story_id,
            "original": self.original,
            "simulated": self.simulated,
            "changed": self.changed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SimulationReport:
    """The full verdict-by-verdict diff for one proposed change."""

    proposed_errors: tuple[str, ...] = ()
    verdicts: tuple[VerdictDiff, ...] = ()

    @property
    def changed(self) -> list[VerdictDiff]:
        return [diff for diff in self.verdicts if diff.changed]

    @property
    def unchanged(self) -> list[VerdictDiff]:
        return [diff for diff in self.verdicts if not diff.changed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposedErrors": list(self.proposed_errors),
            "verdictCount": len(self.verdicts),
            "changedCount": len(self.changed),
            "verdicts": [diff.to_dict() for diff in self.verdicts],
        }


def _read_detail(ledger: Ledger, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def _acp_allows(pack: PolicyPack, adapter_id: str, state: str, tool_kind: str) -> bool:
    """The FR-M34-04 allow-list replay: the adapter's entry (or ``*``);
    ``deny`` before ``allow``; a kind on both is denied. A fail-closed
    pack carries an empty allow-list, so everything is denied — exactly
    the live path's fail-closed behaviour."""
    adapters = pack.acp_permissions.get("adapters", {})
    if not isinstance(adapters, Mapping):
        return False
    specific = adapters.get(adapter_id)
    fallback = adapters.get("*")
    rules = specific if isinstance(specific, Mapping) else fallback
    if not isinstance(rules, Mapping):
        return False
    allowed = rules.get(state, [])
    # Deny before allow: the '*' and the specific deny lists both apply —
    # a kind on either is denied (the same rule the host's policy.ts uses).
    denied: list[Any] = []
    for entry in (fallback, specific):
        if isinstance(entry, Mapping) and isinstance(entry.get("deny"), list):
            denied.extend(entry["deny"])
    return (
        isinstance(allowed, list)
        and tool_kind in allowed
        and tool_kind not in denied
    )


def _replay_gate(
    row: Mapping[str, Any], detail: Mapping[str, Any], proposed: PolicyPack
) -> VerdictDiff:
    packet = detail.get("packet")
    profile = detail.get("gate")
    story_id = str(row.get("story_id") or "")
    original = str(row.get("decision") or "")
    if not isinstance(packet, Mapping) or not isinstance(profile, str) or not profile:
        return VerdictDiff(
            sequence=int(row["seq"]),
            action_type=GATE_ACTION,
            story_id=story_id,
            original=original,
            simulated="unknown",
            changed=False,
            reason="inputs not recorded — a proposal can only be explained "
            "over verdicts whose packet and profile were recorded (P26)",
        )
    verdict = governance_engine.evaluate(packet, profile.strip(), proposed)
    simulated = "approved" if verdict.passed else "rejected"
    if verdict.fail_closed:
        reason = "proposed pack fails closed: " + "; ".join(verdict.reasons)
    elif simulated == original:
        reason = "no change: the proposed pack reaches the same verdict"
    else:
        reason = "proposed pack: " + "; ".join(verdict.reasons or ["criteria pass"])
    return VerdictDiff(
        sequence=int(row["seq"]),
        action_type=GATE_ACTION,
        story_id=story_id,
        original=original,
        simulated=simulated,
        changed=simulated != original,
        reason=reason,
    )


def _replay_permission(
    row: Mapping[str, Any], detail: Mapping[str, Any], proposed: PolicyPack
) -> VerdictDiff:
    story_id = str(row.get("story_id") or "")
    original = str(row.get("decision") or "")
    adapter_id = detail.get("adapterId")
    tool_kind = detail.get("toolKind")
    state = detail.get("adapterState")
    if (
        not isinstance(adapter_id, str)
        or not isinstance(tool_kind, str)
        or not isinstance(state, str)
    ):
        return VerdictDiff(
            sequence=int(row["seq"]),
            action_type=PERMISSION_ACTION,
            story_id=story_id,
            original=original,
            simulated="unknown",
            changed=False,
            reason="inputs not recorded (adapterId/toolKind/adapterState) — "
            "a proposal can only be explained over verdicts whose "
            "allow-list inputs were recorded (P26)",
        )
    allowed = _acp_allows(proposed, adapter_id, state, tool_kind)
    simulated = "approved" if allowed else "rejected"
    if simulated == original:
        reason = "no change: the proposed allow-list reaches the same decision"
    elif allowed:
        reason = (
            f"proposed allow-list grants {tool_kind} to adapter "
            f"'{adapter_id}' in state '{state}' — the policy gate would "
            "no longer deny the request"
        )
    else:
        reason = (
            f"proposed allow-list does not grant {tool_kind} to adapter "
            f"'{adapter_id}' in state '{state}' — the policy gate would "
            "deny the request before the human saw it"
        )
    return VerdictDiff(
        sequence=int(row["seq"]),
        action_type=PERMISSION_ACTION,
        story_id=story_id,
        original=original,
        simulated=simulated,
        changed=simulated != original,
        reason=reason,
    )


def simulate_policy_change(
    ledger: Ledger,
    proposed_text: str,
    *,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    limit: int | None = None,
) -> SimulationReport:
    """Replay ``proposed_text`` (a full policy-pack YAML document) against
    the historical gate and permission verdicts in the slice. Read-only
    and deterministic: the ledger is queried, never appended."""
    proposed = parse_policy_pack(proposed_text, "proposed")
    rows: list[dict[str, Any]] = []
    for action_type in _SIMULATED_ACTIONS:
        rows.extend(
            ledger.query_all(
                action_type=action_type,
                from_sequence=from_sequence,
                to_sequence=to_sequence,
                max_rows=limit,
            )
        )
    rows.sort(key=lambda row: row["seq"])
    diffs = []
    for row in rows:
        detail = _read_detail(ledger, row)
        if row["action_type"] == GATE_ACTION:
            diffs.append(_replay_gate(row, detail, proposed))
        else:
            diffs.append(_replay_permission(row, detail, proposed))
    return SimulationReport(
        proposed_errors=tuple(proposed.errors), verdicts=tuple(diffs)
    )
