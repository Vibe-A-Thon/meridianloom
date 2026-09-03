"""External-agent observers (FR-M35-02, FR-M35-08; F0 Workstream D).

Public surface: the confidence model and fallback chain (``base``), the
registry with health reporting (``manager``), and the per-vendor adapters
(``claude``, ``copilot``).

SEC-27: this package MUST stay free of Meridian credentials, policy and
ledger key material — observed agents are observed one-way. The tests in
test_observer_isolation.py enforce that contract; do not import
``meridian_core.ledger`` here.
"""

from __future__ import annotations

from .base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CHAIN_OTEL,
    CHAIN_SCM_API,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_ORDER,
    CONFIDENCE_TELEMETRY,
    FALLBACK_CHAIN,
    EvidenceTier,
    Observation,
    TelemetryFormatError,
    run_fallback_chain,
)

__all__ = [
    "CHAIN_FILESYSTEM",
    "CHAIN_GIT_TRAILERS",
    "CHAIN_OTEL",
    "CHAIN_SCM_API",
    "CONFIDENCE_DIRECT",
    "CONFIDENCE_INFERRED",
    "CONFIDENCE_ORDER",
    "CONFIDENCE_TELEMETRY",
    "FALLBACK_CHAIN",
    "EvidenceTier",
    "Observation",
    "TelemetryFormatError",
    "run_fallback_chain",
]
