"""Observer framework tests (FR-M35-08, FR-M35-02, NFR-32, G3).

Task 17: the versioned observer interface, the manager registry with
health reporting, and the documented fallback chain with confidence
downgrade — including the format-change simulation that proves a broken
telemetry format degrades to the next tier WITH A VISIBLE WARNING, never
silence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from meridian_core.observers import base
from meridian_core.observers.base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CHAIN_OTEL,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_TELEMETRY,
    FALLBACK_CHAIN,
    EvidenceTier,
    Observation,
    TelemetryFormatError,
    run_fallback_chain,
)
from meridian_core.observers.manager import STATUS_DEGRADED, STATUS_OK, ObserverManager

NOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)


def make_observation(confidence: str, source: str, vendor: str = "acme") -> Observation:
    return Observation(
        vendor=vendor,
        session_id=f"{source}-session",
        confidence=confidence,
        source=source,
        detail=f"evidence from {source}",
        started_at=NOW.isoformat(),
    )


class FakeObserver:
    """Minimal Observer-protocol implementation for framework tests."""

    def __init__(self, vendor: str, outcome: base.ChainOutcome | None = None) -> None:
        self.vendor = vendor
        self.vendor_release = "1.0.0"
        self.adapter_version = "1.0.0"
        self._outcome = outcome or base.ChainOutcome(observation=None)
        self.calls = 0

    def observe(self, workspace: Path, now: datetime) -> base.ChainOutcome:
        self.calls += 1
        return self._outcome

    def health(self) -> dict:
        return {"detail": f"probe for {self.vendor}"}


class TestFallbackChain:
    def test_chain_order_is_the_documented_fr_m35_02_order(self):
        # FR-M35-02 preference order; ACP is first but not in F0.
        assert FALLBACK_CHAIN == ("acp", "otel", "git-trailers", "scm-api", "filesystem")

    def test_first_tier_with_evidence_wins(self):
        tiers = [
            EvidenceTier(CHAIN_OTEL, CONFIDENCE_TELEMETRY, lambda ws, now: None),
            EvidenceTier(
                CHAIN_GIT_TRAILERS,
                CONFIDENCE_TELEMETRY,
                lambda ws, now: make_observation(CONFIDENCE_TELEMETRY, "git-trailers"),
            ),
            EvidenceTier(
                CHAIN_FILESYSTEM,
                CONFIDENCE_INFERRED,
                lambda ws, now: make_observation(CONFIDENCE_INFERRED, "filesystem"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation is not None
        assert outcome.observation.source == "git-trailers"
        assert outcome.tiers_tried == [CHAIN_OTEL, CHAIN_GIT_TRAILERS]

    def test_format_change_degrades_to_next_tier_with_warning(self):
        # NFR-32 / G3: a telemetry format change must downgrade AND warn.
        def broken_otel(ws, now):
            raise TelemetryFormatError("span schema v9: missing attribute 'session.id'")

        tiers = [
            EvidenceTier(CHAIN_OTEL, CONFIDENCE_DIRECT, broken_otel),
            EvidenceTier(
                CHAIN_GIT_TRAILERS,
                CONFIDENCE_TELEMETRY,
                lambda ws, now: make_observation(CONFIDENCE_TELEMETRY, "git-trailers"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY
        assert outcome.degraded_from == CHAIN_OTEL
        assert outcome.warnings, "downgrade must be visible, never silent"
        assert "NFR-32" in outcome.warnings[0]

    def test_format_change_falls_to_filesystem_when_all_else_empty(self):
        def broken_otel(ws, now):
            raise TelemetryFormatError("unknown payload")

        tiers = [
            EvidenceTier(CHAIN_OTEL, CONFIDENCE_DIRECT, broken_otel),
            EvidenceTier(CHAIN_GIT_TRAILERS, CONFIDENCE_TELEMETRY, lambda ws, now: None),
            EvidenceTier(
                CHAIN_FILESYSTEM,
                CONFIDENCE_INFERRED,
                lambda ws, now: make_observation(CONFIDENCE_INFERRED, "filesystem"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert len(outcome.warnings) == 1

    def test_unavailable_tier_is_not_vendor_drift(self):
        # A missing export dir (None) must NOT warn — only format changes do.
        tiers = [
            EvidenceTier(CHAIN_OTEL, CONFIDENCE_DIRECT, lambda ws, now: None),
            EvidenceTier(
                CHAIN_FILESYSTEM,
                CONFIDENCE_INFERRED,
                lambda ws, now: make_observation(CONFIDENCE_INFERRED, "filesystem"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation is not None
        assert outcome.warnings == []
        assert outcome.degraded_from is None

    def test_a_tier_cannot_overclaim_confidence(self):
        # UI-boundary rule: the framework clamps a tier to its rung ceiling.
        tiers = [
            EvidenceTier(
                CHAIN_GIT_TRAILERS,
                CONFIDENCE_TELEMETRY,
                lambda ws, now: make_observation(CONFIDENCE_DIRECT, "git-trailers"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY

    def test_broken_non_drift_tier_is_skipped_silently(self):
        tiers = [
            EvidenceTier(
                CHAIN_OTEL,
                CONFIDENCE_DIRECT,
                lambda ws, now: (_ for _ in ()).throw(RuntimeError("no collector")),
                drift_sensitive=False,
            ),
            EvidenceTier(
                CHAIN_FILESYSTEM,
                CONFIDENCE_INFERRED,
                lambda ws, now: make_observation(CONFIDENCE_INFERRED, "filesystem"),
            ),
        ]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation.source == "filesystem"
        assert outcome.warnings == []

    def test_no_evidence_anywhere_is_honest_none_not_an_error(self):
        tiers = [EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, lambda ws, now: None)]
        outcome = run_fallback_chain("acme", tiers, Path("."), NOW)
        assert outcome.observation is None
        assert outcome.tiers_tried == [CHAIN_FILESYSTEM]

    def test_unknown_tier_or_confidence_is_a_build_error(self):
        with pytest.raises(ValueError, match="unknown fallback-chain tier"):
            run_fallback_chain(
                "acme", [EvidenceTier("smoke-signals", "inferred", lambda ws, now: None)], Path("."), NOW
            )
        with pytest.raises(ValueError, match="unknown confidence"):
            run_fallback_chain(
                "acme",
                [EvidenceTier(CHAIN_OTEL, "psychic", lambda ws, now: None)],
                Path("."),
                NOW,
            )


class TestManager:
    def test_registry_runs_every_observer_once_per_observe(self):
        first = FakeObserver("vendor-a", base.ChainOutcome(make_observation(CONFIDENCE_INFERRED, "filesystem", "vendor-a")))
        second = FakeObserver("vendor-b", base.ChainOutcome(make_observation(CONFIDENCE_TELEMETRY, "git-trailers", "vendor-b")))
        manager = ObserverManager([first, second])
        observations = manager.observe(Path("."), now=NOW)
        assert {o.vendor for o in observations} == {"vendor-a", "vendor-b"}
        assert first.calls == 1 and second.calls == 1

    def test_health_ok_when_no_warnings(self):
        manager = ObserverManager([FakeObserver("vendor-a")])
        records = manager.health()
        assert len(records) == 1
        assert records[0]["status"] == STATUS_OK
        assert records[0]["name"] == "vendor-a"
        assert records[0]["vendorRelease"] == "1.0.0"
        assert records[0]["warnings"] == []

    def test_downgrade_warning_is_sticky_for_the_session(self):
        # NFR-32: "within one session" — the warning survives later observe()
        # calls even when the chain would now succeed.
        outcome = base.ChainOutcome(
            observation=make_observation(CONFIDENCE_TELEMETRY, "git-trailers"),
            warnings=["acme: otel telemetry format changed; degraded (NFR-32)"],
            degraded_from=CHAIN_OTEL,
        )
        observer = FakeObserver("acme", outcome)
        manager = ObserverManager([observer])
        manager.observe(Path("."), now=NOW)
        manager.observe(Path("."), now=NOW)  # second run produces no new warning
        (record,) = manager.health()
        assert record["status"] == STATUS_DEGRADED
        assert len(record["warnings"]) == 1  # retained once, still visible
        assert manager.warnings("acme") == record["warnings"]

    def test_health_probe_crash_becomes_degraded_not_a_crash(self):
        class SickObserver(FakeObserver):
            def health(self):
                raise RuntimeError("probe kaput")

        manager = ObserverManager([SickObserver("sick")])
        (record,) = manager.health()
        assert record["status"] == STATUS_DEGRADED
        assert "probe kaput" in record["warnings"][0]

    def test_observer_interface_is_versioned(self):
        # FR-M35-08: every adapter declares vendor release + adapter version.
        observer = FakeObserver("acme")
        assert isinstance(observer.vendor_release, str) and observer.vendor_release
        assert isinstance(observer.adapter_version, str) and observer.adapter_version


class TestFormatChangeSimulation:
    """The NFR-32 acceptance scenario: simulate a vendor telemetry format
    change end-to-end through the manager and prove downgrade + warning."""

    def test_simulated_format_change_produces_downgrade_and_visible_warning(self):
        class FormatDriftObserver:
            vendor = "driftcorp"
            vendor_release = "2.0.0"
            adapter_version = "1.0.0"

            def __init__(self) -> None:
                self.format_version = "v1"  # flips to "v2" to simulate the vendor drift

            def observe(self, workspace: Path, now: datetime) -> base.ChainOutcome:
                def otel(ws, when):
                    if self.format_version != "v1":
                        raise TelemetryFormatError(
                            f"export format {self.format_version}: expected session.id"
                        )
                    return make_observation(CONFIDENCE_DIRECT, "otel", self.vendor)

                return run_fallback_chain(
                    self.vendor,
                    [
                        EvidenceTier(CHAIN_OTEL, CONFIDENCE_DIRECT, otel),
                        EvidenceTier(
                            CHAIN_GIT_TRAILERS,
                            CONFIDENCE_TELEMETRY,
                            lambda ws, when: make_observation(
                                CONFIDENCE_TELEMETRY, "git-trailers", self.vendor
                            ),
                        ),
                    ],
                    workspace,
                    now,
                )

            def health(self) -> dict:
                return {"detail": f"format {self.format_version}"}

        observer = FormatDriftObserver()
        manager = ObserverManager([observer])
        before = manager.observe(Path("."), now=NOW)
        assert before[0].confidence == CONFIDENCE_DIRECT

        observer.format_version = "v2"  # the vendor ships a new telemetry format
        after = manager.observe(Path("."), now=NOW)
        assert after[0].confidence == CONFIDENCE_TELEMETRY  # degraded
        assert after[0].source == "git-trailers"

        (record,) = manager.health()
        assert record["status"] == STATUS_DEGRADED
        assert record["warnings"], "never silent: the downgrade is visible"
        assert "format changed" in record["warnings"][0]
