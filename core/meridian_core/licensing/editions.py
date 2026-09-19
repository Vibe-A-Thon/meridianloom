"""Which capabilities are free and which need a Premium licence.

This file is the **one place** that decides. Editing the product's commercial
line means editing the two tables below and nothing else; the enforcement code
(``runtime.LicenceManager.check_method``) and the documentation test
(``test_licensing_editions.py``, which fails if a capability is added to
``shared/schema/tiers.json`` without a decision here) follow from it.

The line as shipped:

**Community (free, no key)** — the whole Flight Recorder tier: the
hash-chained signed ledger, line-level attribution, cross-vendor observers,
provenance hooks, evidence-bundle export and the standalone verifier,
interoperability, rejection measurement, spend tracking and the simulation
core. Enough to *know what your agents did and prove it*, permanently, at no
cost, for any number of developers.

**Premium (licence key)** — the features that *act* on that knowledge at
organisational scale:

* ``governor`` — hosted-agent runs, policy gates, N-of-M approvals, roles and
  delegation, identity revocation, worktree isolation, PR gating, steering,
  the MCP gateway, decision records, portability, tenancy and the trainer;
* ``orchestra`` — the six canonical loops, model routing, the tool surface,
  memory, comprehension and adapter management;
* ``analytics`` — management reporting: agent comparison, the J-curve,
  DORA export, spend forecasting and ceiling checks, and the evidence gate.
"""

from __future__ import annotations

from .. import tiers as tier_registry

#: tier -> premium feature group; tiers absent from this table are Community.
PREMIUM_TIERS: dict[str, str] = {
    "governor": "governor",
    "orchestra": "orchestra",
}

#: Individual methods inside an otherwise-Community capability that are
#: Premium. Kept short and explicit: every entry is a commercial decision.
PREMIUM_METHOD_OVERRIDES: dict[str, str] = {
    "trust/compareAgents": "analytics",
    "trust/jcurve": "analytics",
    "trust/tokenmaxxing": "analytics",
    "trust/doraExport": "analytics",
    "evidence/gate": "analytics",
    "spend/forecast": "analytics",
    "spend/ceilingCheck": "analytics",
}

#: Methods that must always work, whatever the licence state. Licence
#: management itself is here: you can always install, inspect and remove a
#: licence, otherwise an expired one could never be replaced.
ALWAYS_AVAILABLE: frozenset[str] = frozenset(
    {"handshake", "ping", "shutdown", "health", "licence/status", "licence/install", "licence/remove"}
)


def required_feature(method: str) -> str | None:
    """The Premium feature group ``method`` needs, or None if it is free."""
    if method in ALWAYS_AVAILABLE:
        return None
    override = PREMIUM_METHOD_OVERRIDES.get(method)
    if override is not None:
        return override
    capability = tier_registry.capability_for_method(method)
    if capability is None:
        return None
    return PREMIUM_TIERS.get(capability["tier"])


def feature_table() -> list[dict[str, str]]:
    """Every capability with its edition — the source for the documentation
    matrix in LICENSING.md and for the completeness test."""
    import bus_types

    rows: list[dict[str, str]] = []
    for capability in bus_types.CAPABILITIES:
        feature = PREMIUM_TIERS.get(capability["tier"])
        rows.append(
            {
                "capability": capability["id"],
                "tier": capability["tier"],
                "edition": "premium" if feature else "community",
                "feature": feature or "",
                "overrides": ", ".join(
                    sorted(m for m in capability["rpcMethods"] if m in PREMIUM_METHOD_OVERRIDES)
                ),
            }
        )
    return rows
