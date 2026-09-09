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

FR-M42-01/02: when the caller presents the signed merge authorisation
(merge_authorisation.py) plus the live SCM binding, the gate additionally
requires the binding to hold — invalidation names the violated field.

Zero model calls (FR-M36-07): the check reads the ledger and the pack only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..ledger.core import Ledger
from . import approval_class, merge_authorisation
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
    """One recorded human approval, decoded from the ledger.

    ``approved_by_class`` is the D40 closed-vocabulary class the approver
    was stamped/classified with (FR-M42-07); a class that is not human
    (FR-M42-08) never reaches this dataclass from the gate's collectors —
    it is rejected with a named note instead.
    """

    sequence: int
    approver: HumanIdentity
    role: str | None
    subject: str
    commit: str
    ts: str = ""
    approved_by_class: str = "unknown"
    approved_by_class_version: str = approval_class.CLASSIFIER_VERSION


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
    required_approvals: int  # FR-M20-04: distinct approvers needed (N-of-M)
    approvals: tuple[Approval, ...]  # the valid approvals the count used


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


def _decode_actor(human_actor: str) -> HumanIdentity:
    name, _, email = human_actor.rpartition("<")
    if "<" in human_actor:
        return HumanIdentity(name=name.strip(), email=email.rstrip(">").strip())
    return HumanIdentity(name=human_actor, email="")


def _row_class(
    detail: dict[str, Any], identity: HumanIdentity
) -> tuple[str, str]:
    """The approval's D40 class: the recorded ``approvedBy`` stamp when the
    row carries one (FR-M42-07), else classification at read time from the
    recorded identity (rows written before the stamp existed)."""
    recorded = detail.get("approvedBy")
    if isinstance(recorded, dict):
        cls = recorded.get("class")
        if approval_class.is_known_class(cls):
            version = recorded.get("classifierVersion")
            return cls, str(version or approval_class.CLASSIFIER_VERSION)
    return (
        approval_class.classify(identity.name, identity.email),
        approval_class.CLASSIFIER_VERSION,
    )


def _non_human_note(seq: int, human_actor: str, cls: str, version: str) -> str:
    return (
        f"approval at seq {seq} by {human_actor} is approvedBy class "
        f"'{cls}' ({version}) — a non-human class never satisfies a "
        "human-approval policy and never counts as a human approval "
        "(FR-M42-08, AC-44)"
    )


def collect_approvals(
    ledger: Ledger,
    subject: str,
    head_commit: str | None,
    *,
    permitted_roles: "set[str] | None" = None,
    excluded_identities: "set[str] | frozenset[str]" = frozenset(),
) -> tuple[list[Approval], list[str]]:
    """Every approval for ``subject`` valid at ``head_commit``, newest
    first, plus notes explaining the rows that did not count.

    The merge gate consumes this for FR-M20-04 (N-of-M): ``permitted_roles``
    filters approvals recorded by a role the role pack does not let approve
    (a role that may not approve never counts — the note says so), and
    ``excluded_identities`` (lower-cased emails) removes approvals the
    separation-of-duties rule forbids, e.g. the ingester approving their
    own change (FR-M20-03).
    """
    approvals: list[Approval] = []
    notes: list[str] = []
    excluded = {identity.strip().lower() for identity in excluded_identities}
    for row in _iter_approval_rows(ledger):
        if row.get("decision") != APPROVED_DECISION:
            continue
        human_actor = str(row.get("human_actor") or "").strip()
        if not human_actor:
            notes.append(
                f"approval at seq {row['seq']} is anonymous and cannot count (FR-M12-07)"
            )
            continue
        detail = _read_detail(ledger, row)
        if detail.get("subject") != subject:
            continue
        recorded_commit = str(detail.get("commit") or "")
        if head_commit is not None and recorded_commit != head_commit:
            continue
        identity = _decode_actor(human_actor)
        cls, class_version = _row_class(detail, identity)
        if not approval_class.is_human_class(cls):
            # FR-M42-08 / AC-44: a bot approval (e.g. a vendor code-review
            # bot), a ruleset bypass actor, or an unclassifiable identity
            # never counts toward a human-approval policy.
            notes.append(_non_human_note(row["seq"], human_actor, cls, class_version))
            continue
        if identity.email.strip().lower() in excluded:
            notes.append(
                f"approval at seq {row['seq']} by {human_actor} does not count: "
                "FR-M20-03 separation of duties — the identity that ingested "
                "the change cannot approve its own merge gate"
            )
            continue
        role = row.get("human_role")
        role = str(role) if role else None
        if permitted_roles is not None and role not in permitted_roles:
            notes.append(
                f"approval at seq {row['seq']} by {human_actor} holds role "
                f"'{role or 'none'}', which may not approve — it does not count"
            )
            continue
        approvals.append(
            Approval(
                sequence=row["seq"],
                approver=identity,
                role=role,
                subject=subject,
                commit=recorded_commit,
                ts=str(row.get("ts_utc") or ""),
                approved_by_class=cls,
                approved_by_class_version=class_version,
            )
        )
    return approvals, notes


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
        cls, class_version = _row_class(detail, identity)
        if not approval_class.is_human_class(cls):
            # FR-M42-08 / AC-44: the freshest binding is non-human — it is
            # not an approval, and the report says so by name.
            stale_note = _non_human_note(row["seq"], human_actor, cls, class_version)
            continue
        return (
            Approval(
                sequence=row["seq"],
                approver=identity,
                role=str(role) if role else None,
                subject=subject,
                commit=recorded_commit,
                approved_by_class=cls,
                approved_by_class_version=class_version,
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
    required_approvals: int = 1,
    permitted_roles: "set[str] | None" = None,
    excluded_identities: "set[str] | frozenset[str]" = frozenset(),
    authorisation: "merge_authorisation.MergeAuthorisation | None" = None,
    binding: "merge_authorisation.MergeBinding | None" = None,
) -> MergeVerdict:
    """FR-M12-05/07 + FR-M20-03/04: may ``subject`` (branch or PR id) merge
    at ``head_commit``?

    Unprotected branches merge freely. Protected branches need the recorded
    human approvals the policy requires — by default one, or N distinct
    approvers when the role pack's N-of-M threshold says so — each bound to
    the head commit, none by an identity the role pack excludes (SoD), none
    holding a role that may not approve, and no active halt. A fail-closed
    pack refuses every merge.

    FR-M42-01/02 (N2-T02/T03): when the caller presents the FR-M42-01
    signed authorisation (``authorisation``) and the live SCM binding
    (``binding``), the merge additionally requires the authorisation to
    validate — any change to a bound element (head, base, diff digest,
    policy version, evidence, expiry, PR identity) blocks with the
    violated field named. Presenting one without the other is itself a
    block: the credential and the state it is checked against travel
    together. None means the v1 approval-only path, unchanged.

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
            required_approvals=max(1, required_approvals),
            approvals=(),
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
    valid: list[Approval] = []
    required = max(1, required_approvals) if protected else 1
    if protected and not halts:
        valid, notes = collect_approvals(
            ledger,
            subject,
            head_commit,
            permitted_roles=permitted_roles,
            excluded_identities=excluded_identities,
        )
        distinct = {a.approver.email.strip().lower() for a in valid if a.approver.email.strip()}
        if len(distinct) < required:
            if valid:
                missing.append(
                    f"{len(distinct)}/{required} distinct recorded human approvals "
                    f"for '{subject}'"
                    + (f" at head {head_commit}" if head_commit else "")
                )
            else:
                # Preserve the FR-M12-05/07 report shape: the missing
                # approval names a stale binding when one exists.
                stale_approval, stale_note = find_approval(ledger, subject, head_commit)
                del stale_approval
                missing.append(
                    f"no recorded human approval for '{subject}'"
                    + (f" at head {head_commit}" if head_commit else "")
                    + (f"; {stale_note}" if stale_note else "")
                )
            missing.extend(notes)
        if valid:
            approval = valid[0]

    if protected and not halts and (authorisation is not None or binding is not None):
        # FR-M42-01/02: the signed authorisation must validate against
        # the live binding; every violation names its field so the block
        # carries a readable reason (AC-45).
        if authorisation is None or binding is None:
            missing.append(
                "merge authorisation incomplete (FR-M42-01): the signed "
                "authorisation and the SCM binding it is checked against "
                "must be presented together"
            )
        else:
            auth_verdict = merge_authorisation.evaluate_authorisation(
                authorisation, binding
            )
            if not auth_verdict.allowed:
                missing.extend(auth_verdict.notes)

    allowed = not missing
    return MergeVerdict(
        allowed=allowed,
        status="approved" if allowed else "blocked",
        subject=subject,
        head_commit=head_commit,
        required_approval=protected,
        halted=bool(halts),
        approval=approval,
        missing=tuple(missing),
        required_approvals=required,
        approvals=tuple(valid),
    )
