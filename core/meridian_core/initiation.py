"""Run initiation — M40, MV2.

`gaps_initiation.md` found the product had forty-four screens and no start
button. The workbench can dispatch work now, so that half is answered; what
was still missing is a **single contract**. Eight doors reach the runtime —
the command palette, the workbench, the Omnibar, chat, an editor context
menu, a dropped file, a connector, the API — and without one object between
them and the runtime there is no single place where preflight, authority and
origin are guaranteed. Four doors would mean four provenance shapes and
"how did this run start?" becomes unanswerable.

    UI ─┐
 palette├─→  RunRequest  ─→  preflight  ─→  authorise  ─→  the runtime
   chat ┘         │              │              │
                  └──────────────┴──────────────┴─→ ledger: origin, identity

**One contract, many doors.** The door is recorded as `origin`; nothing else
about the run differs by door (FR-M40-01/02, AC-38).

The MVP builds the invariant, not all eleven of M40's requirements.
`FR-M40-04` (dry-run default), `06` (per-run overrides), `07` (content
provenance), `08` (editor context) and `10` (templates) stay POST-MVP and
stay specified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

#: FR-M40-02. Closed, and identical to the CHECK constraint the ledger has
#: carried since schema v2 — the storage half of M40 was built before the
#: contract half, so this vocabulary is not a new decision, it is the one
#: already enforced at the database. A value outside it fails there too,
#: which is the belt to this brace.
ORIGINS: tuple[str, ...] = (
    "ui",
    "command",
    "omnibar",
    "chat",
    "editor",
    "file",
    "connector",
    "api",
)

Origin = Literal["ui", "command", "omnibar", "chat", "editor", "file", "connector", "api"]

#: FR-M40-03's six questions. Preflight is refused unless every one is
#: answered, because a preflight missing a field is worse than none: it asks
#: for a confirmation the human cannot actually give.
PREFLIGHT_FIELDS: tuple[str, ...] = (
    "intent",
    "adapters",
    "target",
    "estimate",
    "gates",
    "mode",
)

MODES: tuple[str, ...] = ("dry_run", "live")


class InitiationError(Exception):
    """A run that must not start. Carries a machine-readable code so the
    surface can render the refusal rather than a stack trace."""

    def __init__(self, code: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RunRequest:
    """The one object every door constructs (FR-M40-01).

    Frozen: a request is a record of what was asked for, and a mutable one
    could be edited between preflight and start — which would make the
    human's confirmation a confirmation of something else.
    """

    run_id: str
    origin: str
    created_at: str
    intent: str
    repo: str
    base_branch: str
    adapters: dict[str, str] = field(default_factory=dict)
    mode: str = "dry_run"
    gates: tuple[str, ...] = ()
    cost_ceiling_usd: float | None = None
    estimate_usd: float | None = None
    origin_detail: dict[str, Any] = field(default_factory=dict)
    authorised_by: str | None = None
    authorised_assurance: str | None = None

    @property
    def branch(self) -> str:
        """The branch this run would create. Derived, never supplied — two
        doors passing different branches for the same run id is exactly the
        divergence the single contract exists to prevent."""
        return f"meridian/{self.run_id}"

    @property
    def worktree(self) -> str:
        return f".meridian/worktrees/{self.run_id}"


def new_run_id(*, now: datetime | None = None) -> str:
    """Sortable and unique. Time-ordered so a ledger read in sequence order
    and a run list read by id agree about what happened first."""
    moment = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S")
    return f"run_{moment}_{uuid.uuid4().hex[:8]}"


def build_run_request(
    *,
    origin: str,
    intent: str,
    repo: str,
    base_branch: str = "main",
    adapters: dict[str, str] | None = None,
    mode: str = "dry_run",
    gates: tuple[str, ...] | list[str] = (),
    cost_ceiling_usd: float | None = None,
    estimate_usd: float | None = None,
    origin_detail: dict[str, Any] | None = None,
    now: datetime | None = None,
    run_id: str | None = None,
) -> RunRequest:
    """The only constructor. Every door comes through here (FR-M40-01).

    Validates what cannot be validated later: an origin outside the closed
    vocabulary, an unknown mode, an empty intent. Each is refused here rather
    than at the database, so the message names the door rather than a CHECK
    constraint.
    """
    if origin not in ORIGINS:
        raise InitiationError(
            "ORIGIN_UNKNOWN",
            f"origin {origin!r} is not one of {', '.join(ORIGINS)}. "
            "FR-M40-02: the door a run came through is recorded from a "
            "closed vocabulary, so 'how did this start?' always has an answer.",
            origin=origin,
        )
    if mode not in MODES:
        raise InitiationError(
            "MODE_UNKNOWN", f"mode {mode!r} is not one of {', '.join(MODES)}", mode=mode
        )
    if not intent.strip():
        raise InitiationError(
            "INTENT_EMPTY",
            "a run needs an intent: preflight echoes it back in Meridian's "
            "words, and there is nothing to echo",
        )
    if not repo.strip():
        raise InitiationError("REPO_EMPTY", "a run needs a repository")

    return RunRequest(
        run_id=run_id or new_run_id(now=now),
        origin=origin,
        created_at=(now or datetime.now(timezone.utc)).isoformat(),
        intent=intent.strip(),
        repo=repo.strip(),
        base_branch=base_branch.strip() or "main",
        adapters=dict(adapters or {}),
        mode=mode,
        gates=tuple(gates),
        cost_ceiling_usd=cost_ceiling_usd,
        estimate_usd=estimate_usd,
        origin_detail=dict(origin_detail or {}),
    )


@dataclass(frozen=True)
class Preflight:
    """What the human is shown before anything happens (FR-M40-03)."""

    run_id: str
    origin: str
    intent: str
    adapters: dict[str, str]
    repo: str
    base_branch: str
    branch: str
    worktree: str
    estimate_usd: float | None
    cost_ceiling_usd: float | None
    gates: tuple[str, ...]
    mode: str
    missing: tuple[str, ...]

    @property
    def confirmable(self) -> bool:
        return not self.missing

    def as_wire(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "origin": self.origin,
            "intent": self.intent,
            "adapters": dict(self.adapters),
            "repo": self.repo,
            "baseBranch": self.base_branch,
            "branch": self.branch,
            "worktree": self.worktree,
            "estimateUsd": self.estimate_usd,
            "costCeilingUsd": self.cost_ceiling_usd,
            "gates": list(self.gates),
            "mode": self.mode,
            "confirmable": self.confirmable,
            "missing": list(self.missing),
        }


def preflight(
    request: RunRequest,
    *,
    adapter_usable: Any = None,
) -> Preflight:
    """Assemble the six answers, and name any that are missing.

    A missing field does not raise. The surface needs to *show* what is
    incomplete — refusing with an exception would leave the user with a
    dialog that will not open and no way to see why.

    `adapter_usable` is injected for the same reason the runtime callables
    in `start_run` are: an adapter id that the worktree machinery will
    later reject is an unanswered question, not a runtime failure. Without
    the check, preflight reports `confirmable` for a run that cannot
    start — a human confirms, and the refusal arrives afterwards, naming a
    constraint they were never shown. Injected rather than imported so this
    module keeps depending on nothing.
    """
    missing: list[str] = []
    if not request.intent.strip():
        missing.append("intent")
    if not request.adapters:
        missing.append("adapters")
    elif adapter_usable is not None and not all(
        adapter_usable(adapter) for adapter in request.adapters.values()
    ):
        missing.append("adapters")
    if not request.repo.strip() or not request.base_branch.strip():
        missing.append("target")
    # An estimate of None is missing; an estimate of 0.0 is an answer.
    if request.estimate_usd is None or request.cost_ceiling_usd is None:
        missing.append("estimate")
    if not request.gates:
        missing.append("gates")
    if request.mode not in MODES:
        missing.append("mode")

    return Preflight(
        run_id=request.run_id,
        origin=request.origin,
        intent=request.intent,
        adapters=dict(request.adapters),
        repo=request.repo,
        base_branch=request.base_branch,
        branch=request.branch,
        worktree=request.worktree,
        estimate_usd=request.estimate_usd,
        cost_ceiling_usd=request.cost_ceiling_usd,
        gates=request.gates,
        mode=request.mode,
        missing=tuple(missing),
    )


def authorise(
    request: RunRequest,
    *,
    identity_email: str,
    identity_assurance: str,
    permitted_modes: tuple[str, ...] | list[str],
    requires_verified: bool = False,
) -> RunRequest:
    """Role-check the launch and stamp the identity onto the request.

    SEC-30: a run does not start without an authenticated identity, a
    policy-permitted role for the mode, and a ledger record of who
    authorised it from which origin. The assurance level travels with the
    identity, so a run authorised by a git name is never later read as
    having been authorised by a verified one (FR-M42-04/05 — reused, not
    re-implemented).
    """
    if not identity_email:
        raise InitiationError(
            "IDENTITY_UNAVAILABLE",
            "SEC-30: a run cannot start without an authenticated identity. "
            "An unauthenticated session may not start a run through any door, "
            "including the command palette.",
        )
    if requires_verified and identity_assurance != "verified":
        raise InitiationError(
            "IDENTITY_ASSURANCE_INSUFFICIENT",
            f"policy requires a verified identity to start this run, but "
            f"{identity_email} resolves at assurance {identity_assurance!r}. "
            "A git name and email never satisfies a verified requirement "
            "(FR-M42-05).",
            assurance=identity_assurance,
            required="verified",
        )
    if request.mode not in tuple(permitted_modes):
        raise InitiationError(
            "MODE_NOT_PERMITTED",
            f"{identity_email} is not permitted to start a {request.mode!r} "
            f"run; this role permits {', '.join(permitted_modes) or 'nothing'}. "
            "FR-M40-05: launch authority is role-checked before anything is "
            "created.",
            mode=request.mode,
            permitted=list(permitted_modes),
        )
    return replace(
        request,
        authorised_by=identity_email,
        authorised_assurance=identity_assurance,
    )


def cancellation_record(request: RunRequest, *, reason: str = "") -> dict[str, Any]:
    """The only trace a cancelled run leaves (FR-M40-09).

    Not "no record" — a cancellation is itself a fact worth keeping, and a
    run that vanished without one would be indistinguishable from a run that
    never reached preflight. What it must not leave is a worktree, a branch,
    or any entry implying work began.
    """
    return {
        "actionType": "run_cancelled_at_preflight",
        "runId": request.run_id,
        "origin": request.origin,
        "storyId": request.run_id,
        "decision": "cancelled",
        "humanActor": request.authorised_by,
        "detail": {
            "intent": request.intent,
            "repo": request.repo,
            "mode": request.mode,
            "reason": reason,
            "note": (
                "Cancelled at preflight. No worktree was created, no branch "
                "was created, and no work was dispatched (FR-M40-09)."
            ),
        },
    }


def start_run(
    request: RunRequest,
    *,
    confirmed: bool,
    record_entry: Any,
    create_worktree: Any,
    adapter_usable: Any = None,
) -> dict[str, Any]:
    """The single entry point every door invokes (FR-M40-01).

    The order is the requirement. Preflight must be confirmed and the
    request authorised **before** anything is created, because FR-M40-09's
    guarantee — a cancelled run leaves no worktree and no branch — is only
    achievable if nothing is created until after the human says yes. A
    worktree made optimistically and cleaned up on cancel is a different,
    weaker promise: it depends on the cleanup running.

    `record_entry` and `create_worktree` are injected rather than imported
    so this stays the contract and not a second copy of the runtime. It also
    means the ordering above is testable without a repository on disk.
    """
    if not confirmed:
        raise InitiationError(
            "PREFLIGHT_NOT_CONFIRMED",
            "FR-M40-03: preflight is mandatory and was not confirmed. There "
            "is no skip, and no 'do not show this again' — this is the only "
            "point at which a human sees what is about to be spent and "
            "changed.",
            run_id=request.run_id,
        )
    if not request.authorised_by:
        raise InitiationError(
            "NOT_AUTHORISED",
            "SEC-30: this run was never passed through authorise(); it has "
            "no authorising identity to record.",
            run_id=request.run_id,
        )
    report = preflight(request, adapter_usable=adapter_usable)
    if not report.confirmable:
        raise InitiationError(
            "PREFLIGHT_INCOMPLETE",
            "a confirmation was supplied for a preflight that is not "
            f"answerable: missing {', '.join(report.missing)}",
            missing=list(report.missing),
        )

    # Record BEFORE creating (FR-M10-08, E1: nothing acts without being
    # recorded first), then create.
    entry = record_entry(
        {
            "actionType": "run_started",
            "storyId": request.run_id,
            "decision": "proposed",
            **first_entry_fields(request),
            "detail": {
                "intent": request.intent,
                "repo": request.repo,
                "mode": request.mode,
                "gates": list(request.gates),
                "estimateUsd": request.estimate_usd,
                "costCeilingUsd": request.cost_ceiling_usd,
            },
        }
    )
    worktree = create_worktree(request.branch, request.base_branch, request.worktree)
    return {
        "runId": request.run_id,
        "origin": request.origin,
        "branch": request.branch,
        "worktree": worktree,
        "mode": request.mode,
        "entry": entry,
        "authorisedBy": request.authorised_by,
        "assurance": request.authorised_assurance,
    }


def first_entry_fields(request: RunRequest) -> dict[str, Any]:
    """What the run's first ledger entry carries (FR-M40-02).

    `run_id` and `origin` are the columns the ledger has had since schema
    v2; this is the function that fills them, so every door's first entry
    differs in `origin` and nothing else (AC-38).
    """
    return {
        "runId": request.run_id,
        "origin": request.origin,
        "humanActor": request.authorised_by,
        "humanRole": request.authorised_assurance,
    }
