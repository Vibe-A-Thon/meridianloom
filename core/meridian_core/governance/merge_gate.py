"""The merge gate (FR-M12-05, FR-M12-07; F1 Workstream B task 10).

No merge to a protected branch without a recorded human approval — the rule
holds regardless of autonomy tier, and it applies to external-agent PRs as
much as Meridian's own work (FR-M35-04). CI/SCM connectors (task 12) call
:func:`check_merge` before allowing a merge; the verdict is a plain value:
``allowed`` plus the missing-criteria report, the bound approval's ledger
sequence, and whether a governance halt currently blocks the branch.

Approval binding: ``gate.approve`` records (subject, commit digest,
approver identity, role) in the ledger. An approval whose recorded digest
differs from the current head is INVALIDATED by the changed head — the
report names the stale approval's sequence and digest. Anonymous approval
rows (no recorded human identity) never count. A fail-closed policy pack
refuses every merge.

Zero model calls (FR-M36-07): the check reads the ledger and the pack only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..ledger.core import Ledger
from .identity import HumanIdentity
from .policy import PolicyPack

#: Ledger action_type/decision values this module reads. Written by
#: gate.approve (approval/approved) and gate.halt (gate/halted).
APPROVAL_ACTION = "approval"
GATE_ACTION = "gate"
HALTED_DECISION = "halted"
APPROVED_DECISION = "approved"

#: Halt scopes that block merges. A hosted-session halt targets one ACP
#: session and never gates the merge queue by itself.
MERGE_BLOCKING_SCOPES = ("merge", "observe-only")


@dataclass(frozen=True)
class Approval:
    """One recorded human approval, decoded from the ledger."""

    sequence: int
    approver: HumanIdentity
    role: str | None
    subject: str
    commit: str


@dataclass(frozen=True)
class MergeVerdict:
    """The check_merge result: a decision plus the evidence behind it."""

    allowed: bool
    status: str  # "approved" | "blocked"
    subject: str
    head_commit: str | None
    required_approval: bool
    halted: bool
    approval: Approval | None
    missing: tuple[str, ...]


def _read_detail(ledger: Ledger, row: dict[str, Any]) -> dict[str, Any]:
    ref = row.get("input_ref")
    key_id = row.get("blob_key_id")
    if not ref or not key_id:
        return {}
    try:
        return json.loads(ledger.read_blob(ref, key_id).decode("utf-8"))
    except (ValueError, KeyError, OSError):
        return {}


def _iter_gate_rows(ledger: Ledger) -> list[dict[str, Any]]:
    rows = ledger.query(action_type=GATE_ACTION, limit=1000)
    return list(reversed(rows))  # newest first


def _iter_approval_rows(ledger: Ledger) -> list[dict[str, Any]]:
    rows = ledger.query(action_type=APPROVAL_ACTION, limit=1000)
    return list(reversed(rows))  # newest first


def active_halts(ledger: Ledger, subject: str) -> list[tuple[int, str]]:
    """(sequence, reason) of halt entries currently blocking ``subject``:
    scope merge or observe-only, global (no subject) or bound to this one."""
    halts: list[tuple[int, str]] = []
    for row in _iter_gate_rows(ledger):
        if row.get("decision") != HALTED_DECISION:
            continue
        detail = _read_detail(ledger, row)
        if detail.get("scope") not in MERGE_BLOCKING_SCOPES:
            continue
        halt_subject = detail.get("subject")
        if halt_subject not in (None, "", subject):
            continue
        halts.append((row["seq"], str(row.get("rework_reason") or detail.get("reason") or "halted")))
    return halts


def find_approval(
    ledger: Ledger, subject: str, head_commit: str | None
) -> tuple[Approval | None, str | None]:
    """The freshest approval for ``subject`` valid at ``head_commit``.

    Returns (approval, stale-note): the approval when one binds the head
    (or, with no head given, the newest for the subject), else None and a
    human-readable note naming the invalidated binding when a stale
    approval exists.
    """
    stale_note: str | None = None
    for row in _iter_approval_rows(ledger):
        if row.get("decision") != APPROVED_DECISION:
            continue
        human_actor = str(row.get("human_actor") or "").strip()
        if not human_actor:
            # FR-M12-07: an anonymous row is not an approval; say so.
            stale_note = (
                f"approval at seq {row['seq']} is anonymous and cannot count (FR-M12-07)"
            )
            continue
        detail = _read_detail(ledger, row)
        if detail.get("subject") != subject:
            continue
        recorded_commit = str(detail.get("commit") or "")
        if head_commit is not None and recorded_commit != head_commit:
            if stale_note is None:
                stale_note = (
                    f"approval at seq {row['seq']} is bound to commit "
                    f"{recorded_commit or 'unknown'} and is invalidated by the "
                    f"changed head {head_commit}"
                )
            continue
        role = row.get("human_role")
        name, _, email = human_actor.rpartition("<")
        identity = (
            HumanIdentity(name=name.strip(), email=email.rstrip(">").strip())
            if "<" in human_actor
            else HumanIdentity(name=human_actor, email="")
        )
        return (
            Approval(
                sequence=row["seq"],
                approver=identity,
                role=str(role) if role else None,
                subject=subject,
                commit=recorded_commit,
            ),
            None,
        )
    return None, stale_note


def check_merge(
    ledger: Ledger,
    pack: PolicyPack,
    *,
    subject: str,
    head_commit: str | None = None,
    requires_approval: bool | None = None,
) -> MergeVerdict:
    """FR-M12-05/07: may ``subject`` (branch or PR id) merge at ``head_commit``?

    Unprotected branches merge freely. Protected branches need a recorded
    human approval bound to the head commit, and no active halt. A
    fail-closed pack refuses every merge.

    ``requires_approval`` overrides the protected-branch lookup: ``pr/status``
    passes True when the PR's base branch is protected — a PR subject
    (``pr:repo#n``) is never itself a protected-branch name, but merging it
    lands on one (FR-M35-04). None means "decide from protectedBranches".
    """
    if pack.fail_closed:
        return MergeVerdict(
            allowed=False,
            status="blocked",
            subject=subject,
            head_commit=head_commit,
            required_approval=True,
            halted=False,
            approval=None,
            missing=tuple(pack.errors),
        )

    protected = (
        subject in pack.protected_branches
        if requires_approval is None
        else bool(requires_approval)
    )
    halts = active_halts(ledger, subject)
    missing: list[str] = []
    for seq, reason in halts:
        missing.append(f"merge halted by governance (seq {seq}): {reason}")

    approval: Approval | None = None
    required = protected
    if protected and not halts:
        approval, stale_note = find_approval(ledger, subject, head_commit)
        if approval is None:
            missing.append(
                f"no recorded human approval for '{subject}'"
                + (f" at head {head_commit}" if head_commit else "")
                + (f"; {stale_note}" if stale_note else "")
            )

    allowed = not missing
    return MergeVerdict(
        allowed=allowed,
        status="approved" if allowed else "blocked",
        subject=subject,
        head_commit=head_commit,
        required_approval=required,
        halted=bool(halts),
        approval=approval,
        missing=tuple(missing),
    )
