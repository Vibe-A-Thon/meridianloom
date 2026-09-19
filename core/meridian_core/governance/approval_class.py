"""The closed approval-class vocabulary and classifier (FR-M42-07/08,
FR-M12-07 AMD, AC-44; N1 Workstream D task 18, decision D40).

D40 (closed): Meridian owns this vocabulary; it is VERSIONED (v1) and
growth is a reviewed version bump, never a runtime extension. v1 classes:

* ``human_individual`` — a natural person approving as themselves (the
  identity-provider-resolved human of FR-M20-01, e.g. ``gate.approve``);
* ``human_delegated``  — a natural person exercising a recorded, unexpired
  delegation grant (FR-M20-05) — human authority, delegated;
* ``bot_agent``        — a software actor approving in its own right
  (vendor code-review bots such as Copilot code review, auto-mode
  classifier verdicts, CI identities);
* ``ruleset_actor``    — a repository ruleset / policy rule acting as the
  approver (a policy allow-rule, a ruleset bypass actor, a
  ``denied_by_policy``/allow decision taken by the policy gate);
* ``unknown``          — the honest fallback (P26): a vendor-invented
  approval path that maps onto nothing in the closed set.

Vendor-invented actor types (SCM ``actor.type`` values such as ``Bot``,
``User``, ``Integration``; adapter-invented decision classes) are MAPPED
onto the closed set at capture time; anything unmapped lands on
``unknown``, never on a fabricated class.

FR-M42-08: a non-human class (``bot_agent``, ``ruleset_actor``,
``unknown``) NEVER satisfies a policy requiring human approval and is
never counted as a human approval in any metric. ``human_delegated``
counts as human: the delegation grant is a human act (FR-M20-05).

FR-M42-04 (D38): the class and the identity assurance level are
orthogonal — the class says WHO type acted, the level (``asserted`` |
``verified``) says HOW SURE the identity is. The level rides the stamp
(``identityAssurance``) on human decisions; it never changes the class.

Zero model calls (FR-M36-07): this module is pure stdlib string matching.
"""

from __future__ import annotations

CLASSIFIER_VERSION = "approvedBy/v1"

#: The closed v1 set (D40) — the complete vocabulary, in canonical order.
CLASSES: tuple[str, ...] = (
    "human_individual",
    "human_delegated",
    "ruleset_actor",
    "bot_agent",
    "unknown",
)

#: Classes that satisfy a policy requiring human approval (FR-M42-08).
HUMAN_CLASSES: frozenset[str] = frozenset({"human_individual", "human_delegated"})

#: Classes that NEVER satisfy a human-approval policy and never count as a
#: human approval in a metric (FR-M42-08, AC-44).
NON_HUMAN_CLASSES: frozenset[str] = frozenset(set(CLASSES) - set(HUMAN_CLASSES))

#: Marker substrings that identify a bot/software actor in a recorded
#: identity (name or email). The SCM convention ``[bot]`` is mandatory for
#: Devin (D34) and conventional for every other vendor bot; the named
#: vendor bots are the documented external approvers this gate must not
#: mistake for humans.
_BOT_MARKERS: tuple[str, ...] = (
    "[bot]",
    "github-actions",
    "dependabot",
    "renovate",
    "copilot",
    "devin",
    "codex",
    "claude-ws",
)

#: Marker substrings that identify a ruleset / policy-rule actor.
_RULESET_MARKERS: tuple[str, ...] = (
    "ruleset",
    "bypass",
)

#: Mapping of vendor-invented actor-type strings onto the closed set
#: (capture-time mapping, D40). Keys are lower-cased. Anything not present
#: maps to ``unknown``.
_VENDOR_TYPE_MAP: dict[str, str] = {
    "user": "human_individual",
    "human": "human_individual",
    "human_individual": "human_individual",
    "human_delegated": "human_delegated",
    "delegated": "human_delegated",
    "bot": "bot_agent",
    "app": "bot_agent",
    "agent": "bot_agent",
    "integration": "bot_agent",
    "model_classifier": "bot_agent",
    "classifier": "bot_agent",
    "bot_agent": "bot_agent",
    "policy_rule": "ruleset_actor",
    "policy-rule": "ruleset_actor",
    "ruleset": "ruleset_actor",
    "ruleset_actor": "ruleset_actor",
    "bypass_actor": "ruleset_actor",
}


def is_known_class(value: object) -> bool:
    """True when ``value`` is a member of the closed v1 set."""
    return isinstance(value, str) and value in CLASSES


def is_human_class(value: object) -> bool:
    """FR-M42-08: may this class satisfy a human-approval policy / count
    as a human approval in a metric?"""
    return value in HUMAN_CLASSES


def map_vendor_type(raw: object) -> str:
    """Map a vendor-invented actor/decision type onto the closed set.

    A closed-set member passes through; a known vendor string maps; an
    unknown or absent value is ``unknown`` (P26 — never a residual, never
    invented).
    """
    if not isinstance(raw, str) or not raw.strip():
        return "unknown"
    text = raw.strip()
    if is_known_class(text):
        return text
    return _VENDOR_TYPE_MAP.get(text.lower(), "unknown")


def classify(
    name: str = "",
    email: str = "",
    *,
    declared: object = None,
) -> str:
    """Classify a recorded approver onto the closed v1 set.

    ``declared`` is a capture-time class hint (from the recording surface
    or a vendor actor type): a closed-set member wins outright; a known
    vendor string maps through :func:`map_vendor_type`; any other string
    is classified by its markers only, and an unmapped string with no
    markers is ``unknown`` (P26 — a vendor-invented path never lands on
    ``human_individual`` by default). Without a declared hint the identity
    itself is inspected: ``[bot]``/vendor-bot markers in name or email ->
    ``bot_agent``; ruleset/bypass markers -> ``ruleset_actor``; a non-empty
    human-looking identity -> ``human_individual``; nothing identifiable
    -> ``unknown``.
    """
    if isinstance(declared, str) and declared.strip():
        mapped = map_vendor_type(declared)
        if mapped != "unknown":
            return mapped
        text = declared.strip()
        lowered = text.lower()
        if any(marker in lowered for marker in _BOT_MARKERS) or any(
            marker in lowered for marker in _RULESET_MARKERS
        ):
            return _classify_text(text)
        return "unknown"
    if not name.strip() and not email.strip():
        return "unknown"
    return _classify_text(f"{name} <{email}>" if email else name)


def _classify_text(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in _BOT_MARKERS):
        return "bot_agent"
    if any(marker in lowered for marker in _RULESET_MARKERS):
        return "ruleset_actor"
    return "human_individual"


def stamp(cls: str, identity_assurance: "str | None" = None) -> dict[str, str]:
    """The recorded ``approvedBy`` block: class + classifier version ride
    together on every approval and permission decision (FR-M42-07).

    FR-M42-04 (D38): when the decision is a human act, the identity
    assurance level (``asserted`` | ``verified``) the provider resolved
    rides the same block — ``None`` omits the key (non-human classes and
    pre-FR-M42-04 rows), never fabricates a level."""
    block = {"class": cls, "classifierVersion": CLASSIFIER_VERSION}
    if identity_assurance is not None:
        block["identityAssurance"] = identity_assurance
    return block
