"""FR-M36-05 tier enforcement, sidecar half.

The capability registry lives in shared/schema/tiers.json and is generated
into ``bus_types.CAPABILITIES``; this module is only the lookup and refusal
logic over it. A method whose owning capability sits in a disabled tier is
refused with TIER_DISABLED and a structured, actionable payload — the peer
learns the capability, the tier, what *is* enabled, and how to change it (a
setting flip, no reinstall; G5).

The base tier (flight-recorder) cannot be disabled: it is the product's
honesty floor, and lifecycle methods must answer regardless.
"""

from __future__ import annotations

from typing import Any

import bus_types

BASE_TIER = "flight-recorder"

# method -> owning capability, derived from the generated registry.
_CAPABILITY_BY_METHOD: dict[str, bus_types.CapabilityDefinition] = {
    method: capability
    for capability in bus_types.CAPABILITIES
    for method in capability["rpcMethods"]
}


def normalise_enabled_tiers(requested: Any) -> set[str]:
    """Clamp a config/handshake tier list to known tiers plus the base tier.

    Unknown names are dropped silently here — the extension validates the
    setting host-side; the sidecar's job is to never end up with an empty or
    base-less set, whatever arrives.
    """
    enabled = {
        tier
        for tier in (requested or [])
        if isinstance(tier, str) and tier in bus_types.TIERS
    }
    enabled.add(BASE_TIER)
    return enabled


def capability_for_method(
    method: str,
) -> bus_types.CapabilityDefinition | None:
    return _CAPABILITY_BY_METHOD.get(method)


def is_method_enabled(method: str, enabled_tiers: set[str]) -> bool:
    """Unknown methods are not a tier question — dispatch answers METHOD_NOT_FOUND."""
    capability = _CAPABILITY_BY_METHOD.get(method)
    return capability is None or capability["tier"] in enabled_tiers


def tier_disabled_data(method: str, enabled_tiers: set[str]) -> dict[str, Any]:
    capability = _CAPABILITY_BY_METHOD[method]
    tier = capability["tier"]
    return {
        "method": method,
        "capability": capability["id"],
        "tier": tier,
        "enabledTiers": sorted(enabled_tiers),
        "remediation": (
            f'Enable the {tier} tier by adding "{tier}" to the meridian.tiers '
            "workspace setting; no reinstall is needed (FR-M36-05)."
        ),
    }


def tier_disabled_message(method: str) -> str:
    capability = _CAPABILITY_BY_METHOD[method]
    return (
        f"{method} belongs to the {capability['tier']} tier "
        f"(capability {capability['id']}), which is disabled in this workspace."
    )
