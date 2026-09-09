"""FR-M42-11/12 + SEC-32 + P27 (FUT-025; N2-T05): enforcement-point
declaration.

Every control Meridian displays declares, from a CLOSED versioned
vocabulary, the boundary at which it actually enforces — and whether it
enforces at all. A control that binds in the editor is never described
as enforced (P27: a control is only as strong as the boundary it binds
at; SEC-32: never present a control as enforced where it is not).

The vocabulary is the FR-M42-11 normative set — it is not extensible at
runtime; adding a point is a schema change with a version bump:

* ``editor``          — the text editor's own UI/process
* ``extension_host``  — the VS Code extension host
* ``sidecar``         — the Meridian sidecar (this Python process)
* ``scm``             — the source-control server (a protected-branch
                        check / merge queue; only ever effective when an
                        SCM binding is configured)
* ``ci``              — a CI system
* ``advisory_only``   — observes, records and warns; intercepts nothing

Each :class:`ControlDeclaration` also carries ``boundary_note``: what
could bypass the control and who could do it, in plain words — the
FR-M42-12 test that an independent reviewer given only the audit bundle
can state, per decision, what could have bypassed it.

D37: the FR-M42-03 SCM-native merge check is REFUSED until a pilot
customer exists. The ``scm_merge_check`` control is therefore declared
with point ``scm`` but its EFFECTIVE point in v1 is ``sidecar`` — the
check executes inside Meridian and says so. :func:`effective_declaration`
performs that downgrade; nothing may render an unconfigured ``scm``
claim (the v1 configuration NEVER sets ``scm_binding_configured``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Vocabulary version (FR-M42-11 "closed, versioned"). Bump when the
#: vocabulary or a declaration's semantics change; records carry the
#: version so a bundle is interpretable without this module.
VOCABULARY_VERSION = "m42-1"

#: The closed FR-M42-11 enforcement-point vocabulary. Do not extend at
#: runtime — a point outside this tuple fails every declaration check.
VOCABULARY = (
    "editor",
    "extension_host",
    "sidecar",
    "scm",
    "ci",
    "advisory_only",
)


@dataclass(frozen=True)
class ControlDeclaration:
    """One control's honest enforcement-point declaration (FR-M42-11)."""

    control: str
    enforcement_point: str  # always a member of VOCABULARY
    enforced: bool  # False = advisory: it observes, records, warns
    boundary_note: str  # what could bypass it, and who could do so


#: The control registry (FR-M42-11: "every control Meridian displays").
#: Notes are written to be quoted into an audit bundle verbatim.
CONTROLS: dict[str, ControlDeclaration] = {
    "merge_gate": ControlDeclaration(
        control="merge_gate",
        enforcement_point="sidecar",
        enforced=True,
        boundary_note=(
            "The verdict is computed in the Meridian sidecar and consumed "
            "by CI/SCM connectors. Per D37 it binds IN MERIDIAN: the FR-M42-03 "
            "SCM-native check is refused until a pilot customer configures it, "
            "so a developer who never installs Meridian and merges directly "
            "at the SCM is not intercepted — the ledger records the approval "
            "facts, the SCM does not (yet) enforce them."
        ),
    ),
    "scm_merge_check": ControlDeclaration(
        control="scm_merge_check",
        enforcement_point="scm",
        enforced=True,
        boundary_note=(
            "The FR-M42-03 required status check / merge-queue gate, "
            "evaluated from the FR-M42-01 authorisation binding. REFUSED "
            "until a pilot customer's platform team exists (D37): with no "
            "SCM binding configured this control's effective point is "
            "sidecar and it must never be rendered as enforced at the SCM."
        ),
    ),
    "permission_policy": ControlDeclaration(
        control="permission_policy",
        enforcement_point="sidecar",
        enforced=True,
        boundary_note=(
            "Role permissions and delegations are checked in the sidecar on "
            "the acting identity (gate.approve refuses a role that may not "
            "approve). It binds where it is consulted: actions taken outside "
            "Meridian with no identity in scope are never permitted by this "
            "control, but they are also never intercepted by it."
        ),
    ),
    "halt_all": ControlDeclaration(
        control="halt_all",
        enforcement_point="sidecar",
        enforced=True,
        boundary_note=(
            "gate.halt records the halt in the ledger before returning and "
            "the merge gate refuses while a merge-scope halt is active; the "
            "pause of a running hosted session lands at the host/registry's "
            "next checkpoint, not as an in-flight intercept. A process the "
            "operator cannot reach (a non-Meridian runtime) is recorded "
            "against, not stopped."
        ),
    ),
    "policy_refusal": ControlDeclaration(
        control="policy_refusal",
        enforcement_point="sidecar",
        enforced=True,
        boundary_note=(
            "A fail-closed policy pack refuses every governed decision in "
            "the sidecar, and gate.evaluate rejects against the pack's "
            "criteria. The refusal binds at the surfaces that consult the "
            "sidecar; a surface that never asks is never refused."
        ),
    ),
    "spend_ceiling": ControlDeclaration(
        control="spend_ceiling",
        enforcement_point="sidecar",
        enforced=True,
        boundary_note=(
            "A ceiling breach by a hosted or Meridian-native actor is "
            "recorded in the ledger and dispatches a pause-at-checkpoint "
            "notification; the extension host owns the wire and pauses at "
            "the session's next checkpoint. An OBSERVED external agent gets "
            "an advisory warning only — observation never intercepts "
            "(FR-M35-06), and the warning says so in plain words."
        ),
    ),
    "provenance_hook": ControlDeclaration(
        control="provenance_hook",
        enforcement_point="advisory_only",
        enforced=False,
        boundary_note=(
            "The opt-in commit-msg trailer hook runs as a local git hook: "
            "it never blocks a commit, and git's --no-verify skips it "
            "entirely. A commit made with the hook absent carries no "
            "Meridian-Ledger trailer; the miss is visible in doctor, not "
            "prevented at the SCM."
        ),
    ),
    "steer_checkpoint": ControlDeclaration(
        control="steer_checkpoint",
        enforcement_point="extension_host",
        enforced=True,
        boundary_note=(
            "For sessions Meridian hosts, the extension host pauses the "
            "agent at its next checkpoint on steer/escalate or a spend/halt "
            "dispatch. For OBSERVED external sessions the identical surface "
            "is advisory only — the same NOT_HOSTED honesty: it records and "
            "warns, it never intercepts (FR-M35-06)."
        ),
    ),
}


def is_known_point(point: str) -> bool:
    return point in VOCABULARY


def effective_declaration(
    control: str,
    *,
    scm_binding_configured: bool = False,
) -> ControlDeclaration:
    """The declaration as it actually holds right now (FR-M42-11/12, D37).

    An ``scm``-point control with no SCM binding configured is downgraded
    to ``sidecar`` — that is where the check really executes in v1 — with
    the downgrade stated in the note. v1 never configures the binding, so
    in v1 NOTHING effectively claims ``scm``; this is the function the
    rendering and audit-bundle tests pin down. Unknown controls are a
    programming error and raise KeyError, never a silent default (P26).
    """
    declaration = CONTROLS[control]
    if declaration.enforcement_point != "scm" or scm_binding_configured:
        return declaration
    return replace(
        declaration,
        enforcement_point="sidecar",
        boundary_note=(
            declaration.boundary_note
            + " EFFECTIVE POINT (v1): no SCM binding is configured (D37 — "
            "refused until a pilot customer exists); the check executes in "
            "the sidecar and binds in Meridian only. Never render as "
            "enforced at the SCM."
        ),
    )


def audit_record(declaration: ControlDeclaration) -> dict[str, object]:
    """The per-decision record (FR-M42-12): the effective enforcement
    point, whether the control is enforced, and the bypass note — carried
    in the decision's ledger detail and in the audit bundle's enforcement
    section so a reviewer holding only the bundle can state what could
    have bypassed each decision and who could have done it."""
    return {
        "control": declaration.control,
        "enforcementPoint": declaration.enforcement_point,
        "enforced": declaration.enforced,
        "vocabularyVersion": VOCABULARY_VERSION,
        "boundaryNote": declaration.boundary_note,
    }


def enforcement_section(*, scm_binding_configured: bool = False) -> dict[str, object]:
    """The audit bundle's enforcement section (FR-M42-12, FR-M12-11):
    the vocabulary version and every control's effective declaration."""
    return {
        "vocabularyVersion": VOCABULARY_VERSION,
        "vocabulary": list(VOCABULARY),
        "scmBindingConfigured": bool(scm_binding_configured),
        "controls": {
            name: audit_record(
                effective_declaration(name, scm_binding_configured=scm_binding_configured)
            )
            for name in sorted(CONTROLS)
        },
    }
