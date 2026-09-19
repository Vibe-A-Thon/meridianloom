"""Observer framework core (FR-M35-08, NFR-32, G3).

A *versioned observer interface* per supported external agent, the
documented fallback chain, and the confidence model of FR-M35-02:

    ACP session (not in F0 — Governor tier) -> OTel export
    -> git commit trailers -> filesystem/git inference

Each observation carries an ``observation_confidence``:

* ``direct``    — the agent's own telemetry stream (OTel) identified the
                  session (ACP would also be direct; it lands in F1).
* ``telemetry`` — evidence the agent left behind (git trailers, SCM/PR API).
* ``inferred``  — filesystem/git inference only; the floor, never silence.

NFR-32 / G3: when a vendor's telemetry format changes (a tier raises
:class:`TelemetryFormatError`) the observer DEGRADES to the next fallback
tier and records a visible warning — within the same session, never
silently. Degradation is sticky for the process lifetime: once a tier has
failed, the observer does not pretend the preferred tier is healthy.

Zero model calls (FR-M36-07): this module is pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

# FR-M35-02 observation confidence values, best first.
CONFIDENCE_DIRECT = "direct"
CONFIDENCE_TELEMETRY = "telemetry"
CONFIDENCE_INFERRED = "inferred"
CONFIDENCE_ORDER = (CONFIDENCE_DIRECT, CONFIDENCE_TELEMETRY, CONFIDENCE_INFERRED)

# The documented fallback chain (FR-M35-02). "acp" is listed for honesty —
# it is the preferred tier but does not exist in F0 (F1/Governor hosts ACP
# agents), so no F0 observer implements it.
CHAIN_ACP = "acp"
CHAIN_OTEL = "otel"
CHAIN_GIT_TRAILERS = "git-trailers"
CHAIN_SCM_API = "scm-api"
CHAIN_FILESYSTEM = "filesystem"
FALLBACK_CHAIN = (
    CHAIN_ACP,
    CHAIN_OTEL,
    CHAIN_GIT_TRAILERS,
    CHAIN_SCM_API,
    CHAIN_FILESYSTEM,
)


class TelemetryFormatError(Exception):
    """A vendor's telemetry changed shape (or a check failed) mid-parse.

    Raised by evidence tiers to force the documented downgrade: the chain
    runner catches this, records a visible warning, and moves to the next
    fallback tier (NFR-32). Never raised past the observer boundary.
    """


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Observation:
    """One observed external-agent fact, at one confidence level."""

    vendor: str
    session_id: str
    confidence: str  # direct | telemetry | inferred
    source: str  # which fallback-chain tier produced this (otel, git-trailers, ...)
    detail: str
    started_at: str  # ISO 8601 UTC
    workspace: str | None = None
    agent_id: str | None = None


@dataclass(frozen=True)
class EvidenceTier:
    """One rung of an observer's fallback chain.

    ``name`` must be a FALLBACK_CHAIN member (``acp`` only in F1+).
    ``confidence`` is the ceiling this tier may claim — the framework
    refuses better-than-honest labels (e.g. a trailer tier claiming
    ``direct``).
    """

    name: str
    confidence: str
    scan: Callable[[Path, datetime], Observation | None]
    # When False the tier is simply unavailable (missing tool, no export
    # configured) and the chain moves on WITHOUT a degradation warning —
    # unavailability is not vendor drift. When True, a scan raising
    # TelemetryFormatError (or any error) is vendor drift: warn + degrade.
    drift_sensitive: bool = True


@dataclass
class ChainOutcome:
    """Result of walking one observer's fallback chain."""

    observation: Observation | None
    warnings: list[str] = field(default_factory=list)
    tiers_tried: list[str] = field(default_factory=list)
    degraded_from: str | None = None  # tier name that failed, if downgrade happened


def run_fallback_chain(
    vendor: str,
    tiers: list[EvidenceTier],
    workspace: Path,
    now: datetime,
    sink: WarningSink | None = None,
) -> ChainOutcome:
    """Walk an observer's tiers in preference order (FR-M35-02).

    First tier returning an observation wins. A tier raising
    :class:`TelemetryFormatError` (or any error, when drift-sensitive)
    degrades the chain: the failure becomes a visible warning and the next
    tier is tried. A tier returning None is simply unavailable. The chain
    never raises — an observer that finds nothing reports nothing, and its
    health record carries the warnings so the UI can say why.
    """
    outcome = ChainOutcome(observation=None)
    for tier in tiers:
        if tier.name not in FALLBACK_CHAIN:
            raise ValueError(f"unknown fallback-chain tier: {tier.name}")
        if tier.confidence not in CONFIDENCE_ORDER:
            raise ValueError(f"unknown confidence: {tier.confidence}")
        outcome.tiers_tried.append(tier.name)
        try:
            observation = tier.scan(workspace, now)
        except TelemetryFormatError as error:
            outcome.degraded_from = tier.name
            message = (
                f"{vendor}: {tier.name} telemetry format changed or check failed"
                f" ({error}); degraded to the next fallback tier — observation "
                "continues at lower confidence (NFR-32, never silent)"
            )
            outcome.warnings.append(message)
            if sink is not None:
                sink.warn(vendor, message)
            continue
        except Exception as error:  # noqa: BLE001 - a broken tier must not kill the chain
            if not tier.drift_sensitive:
                continue
            outcome.degraded_from = tier.name
            message = (
                f"{vendor}: {tier.name} check failed ({error!r}); degraded to "
                "the next fallback tier — observation continues at lower "
                "confidence (NFR-32, never silent)"
            )
            outcome.warnings.append(message)
            if sink is not None:
                sink.warn(vendor, message)
            continue
        if observation is None:
            continue
        # Honesty ceiling: a tier may not claim better confidence than its
        # rung allows (the UI-boundary rule for local Claude Code).
        confidence_rank = CONFIDENCE_ORDER.index(observation.confidence)
        tier_rank = CONFIDENCE_ORDER.index(tier.confidence)
        if confidence_rank < tier_rank:
            observation = Observation(
                vendor=observation.vendor,
                session_id=observation.session_id,
                confidence=tier.confidence,
                source=observation.source,
                detail=observation.detail,
                started_at=observation.started_at,
                workspace=observation.workspace,
                agent_id=observation.agent_id,
            )
        outcome.observation = observation
        return outcome
    return outcome


class Observer(Protocol):
    """Versioned observer interface (FR-M35-08).

    Every observer adapter declares which vendor release it is versioned
    against; a format change the adapter cannot parse surfaces as
    :class:`TelemetryFormatError` inside :meth:`observe` (via
    :func:`run_fallback_chain`), producing the documented downgrade.
    """

    vendor: str
    vendor_release: str  # the vendor release this adapter was built against
    adapter_version: str  # our adapter's own version

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome: ...

    def health(self) -> dict: ...
