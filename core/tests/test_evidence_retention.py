"""Vendor evidence retention, volatile capture and expiry (FR-M44-11/12/13,
NFR-37, AC-47; N1 Workstream D tasks 20-22).

FR-M44-11: every supported vendor's documented retention window is
recorded with citation + retrieved date; undocumented windows read
``unknown`` (P26) — never invented. FR-M44-12/NFR-37: captures record
latency, achieved margin and what was unavailable. FR-M44-13/AC-47: a
closed window emits an explicit ``evidence_expired`` marker naming the
window, downgrades observer health/sessions surfaces within one session,
and rides trust-metric envelopes as a named gap — never as an absence of
activity.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.metrics.coverage import DataGap
from meridian_core.metrics.trust import compute_rejection_rate
from meridian_core.observers import retention
from meridian_core.server import SidecarServer

T0 = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
VENDORS = ("claude", "copilot", "cursor", "codex", "devin")


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


# -- T20 / FR-M44-11: the recorded retention windows ---------------------------


class TestRetentionMap:
    def test_all_supported_vendors_recorded(self):
        assert set(retention.VENDOR_RETENTION) == set(VENDORS)

    def test_every_window_is_cited_or_unknown_never_invented(self):
        # P26: a day count exists ONLY with a citation and a retrieved
        # date; an undocumented window is unknown, never a guessed number.
        for vendor, windows in retention.VENDOR_RETENTION.items():
            assert windows, f"{vendor}: at least one evidence source recorded"
            for window in windows:
                assert window.retrieved
                assert window.citation
                if window.documented:
                    assert isinstance(window.window_days, int)
                    assert window.window_days > 0
                else:
                    assert window.window_days is None

    def test_copilot_session_window_is_documented_24_hours(self):
        window = retention.window_for("copilot", "agent-session-logs")
        assert window is not None
        assert window.documented is True
        assert window.window_days == 1
        assert "docs.github.com" in window.citation
        assert window.retrieved == "2026-09-09"

    def test_vendors_without_documented_window_read_unknown(self):
        # futures.md's review (accessed 2026-09-09) documents no retention
        # window for these evidence sources — recorded unknown, not invented.
        for vendor in ("claude", "cursor", "codex", "devin"):
            windows = retention.retention_windows(vendor)
            assert all(w.documented is False for w in windows), vendor
            assert all(w.window_days is None for w in windows), vendor

    def test_unrecorded_source_is_unknown_not_an_error(self):
        window = retention.window_for("copilot", "no-such-source")
        assert window is None
        unknown = retention.unknown_window("copilot", "no-such-source")
        assert unknown.window_days is None
        assert unknown.documented is False

    def test_window_label_names_vendor_source_and_days(self):
        window = retention.window_for("copilot", "agent-session-logs")
        assert window is not None
        assert window.window_label == "copilot agent-session-logs (1 day)"


# -- T21 / FR-M44-12 / NFR-37: capture within the window -----------------------


class TestCapture:
    def test_capture_within_window_records_latency_and_margin(self):
        record = retention.record_capture(
            "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=12)
        )
        assert record.latency_seconds == pytest.approx(43200.0)
        assert record.window_days == 1
        assert record.window_remaining_days == pytest.approx(0.5)
        assert record.achieved_margin == pytest.approx(0.5)
        assert record.within_window is True
        assert record.meets_margin_target is True  # NFR-37: >= 50%

    def test_capture_inside_window_below_margin_target_flagged(self):
        record = retention.record_capture(
            "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=20)
        )
        assert record.within_window is True
        assert record.achieved_margin == round(1 / 6, 6)
        assert record.meets_margin_target is False  # captured, but late

    def test_capture_after_window_is_outside_with_negative_margin(self):
        record = retention.record_capture(
            "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(days=2)
        )
        assert record.within_window is False
        assert record.window_remaining_days == pytest.approx(-1.0)
        assert record.achieved_margin < 0

    def test_unknown_window_cannot_claim_a_margin(self):
        # P26: with no documented window there is no margin to report —
        # the record says unknown instead of inventing one.
        record = retention.record_capture(
            "claude", "local-session-transcripts", T0, captured_at=T0 + timedelta(hours=1)
        )
        assert record.window_days is None
        assert record.achieved_margin is None
        assert record.window_remaining_days is None
        assert record.meets_margin_target is False  # reported, not assumed
        assert record.within_window is False  # nothing provable

    def test_unavailable_evidence_recorded_never_dropped(self):
        record = retention.record_capture(
            "copilot",
            "agent-session-logs",
            T0,
            captured_at=T0 + timedelta(hours=1),
            unavailable=["prompt-transcript", "tool-call-args"],
        )
        assert record.unavailable == ("prompt-transcript", "tool-call-args")

    def test_capture_record_wire_shape(self):
        record = retention.record_capture(
            "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=6)
        )
        payload = record.to_dict()
        assert payload["captureLatencySeconds"] == 21600.0
        assert payload["achievedMargin"] == pytest.approx(0.75)
        assert payload["withinWindow"] is True
        assert payload["meetsMarginTarget"] is True


# -- T22 / FR-M44-13 / AC-47: expiry is marked, not silent ---------------------


class TestExpiry:
    def test_expired_window_emits_named_marker(self):
        tracker = retention.EvidenceExpiryTracker()
        tracker.record(
            retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
        )
        markers = tracker.markers(T0 + timedelta(days=2))
        assert len(markers) == 1
        marker = markers[0]
        assert marker.marker == "evidence_expired"
        assert marker.vendor == "copilot"
        assert marker.source == "agent-session-logs"
        assert marker.window_days == 1
        assert marker.window_label == "copilot agent-session-logs (1 day)"
        assert marker.closed_at == T0 + timedelta(days=1)
        assert "copilot agent-session-logs (1 day)" in marker.message

    def test_open_window_emits_no_marker(self):
        tracker = retention.EvidenceExpiryTracker()
        tracker.record(
            retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
        )
        assert tracker.markers(T0 + timedelta(hours=2)) == []

    def test_unknown_window_never_expires(self):
        tracker = retention.EvidenceExpiryTracker()
        tracker.record(
            retention.record_capture(
                "claude", "local-session-transcripts", T0
            )
        )
        assert tracker.markers(T0 + timedelta(days=3650)) == []
        assert tracker.downgraded is False

    def test_marker_is_sticky_within_the_session(self):
        # AC-47: the downgrade lands within one session and stays visible;
        # a later observation cannot silently reopen the gap.
        tracker = retention.EvidenceExpiryTracker()
        tracker.record(
            retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
        )
        assert tracker.downgraded is False
        tracker.markers(T0 + timedelta(days=2))
        assert tracker.downgraded is True
        tracker.record(
            retention.record_capture(
                "copilot",
                "agent-session-logs",
                T0 + timedelta(days=2),
                captured_at=T0 + timedelta(days=2, hours=1),
            )
        )
        later = tracker.markers(T0 + timedelta(days=3))
        assert len(later) == 1  # the first closed window stays marked

    def test_expiry_rides_the_envelope_as_a_named_gap(self):
        tracker = retention.EvidenceExpiryTracker()
        tracker.record(
            retention.record_capture(
                "copilot", "agent-session-logs", T0, captured_at=T0 + timedelta(hours=1)
            )
        )
        gaps = tracker.gaps(T0 + timedelta(days=2))
        assert len(gaps) == 1
        assert isinstance(gaps[0], DataGap)
        assert gaps[0].gapClass == "evidence_expired"
        assert gaps[0].detail == "copilot agent-session-logs (1 day)"

    def test_metric_envelope_carries_the_gap_not_silence(self):
        # The trust metric over a population that lost volatile evidence
        # names the closed window on the envelope's gaps (FR-M41-12 shape).
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(tmpdir, EphemeralSigningKeyProvider())
            ledger.append(
                {
                    "story_id": "s1",
                    "phase": "build",
                    "loop_id": "loop",
                    "loop_iteration": 1,
                    "actor_id": "agent",
                    "actor_version": "1",
                    "actor_kind": "external",
                    "policy_version": "p",
                    "action_type": "diff",
                }
            )
            tracker = retention.EvidenceExpiryTracker()
            tracker.record(
                retention.record_capture(
                    "copilot",
                    "agent-session-logs",
                    T0,
                    captured_at=T0 + timedelta(hours=1),
                )
            )
            result = compute_rejection_rate(ledger, data_gaps=tracker.gaps(T0 + timedelta(days=2)))
            envelope = result["coverage"]
            gap_classes = [gap["gapClass"] for gap in envelope["gaps"]]
            assert "evidence_expired" in gap_classes
            ledger.close()


# -- server surfaces: RPC wiring ------------------------------------------------


class TestServerSurfaces:
    @pytest.fixture()
    def server(self, tmp_path):
        return SidecarServer(ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()))

    def test_capture_evidence_rpc_records_within_window(self, server):
        response = call(
            server,
            "observe/captureEvidence",
            {
                "vendor": "copilot",
                "source": "agent-session-logs",
                "evidenceTime": T0.isoformat(),
                "capturedAt": (T0 + timedelta(hours=6)).isoformat(),
                "unavailable": ["prompt-transcript"],
            },
        )
        result = response["result"]
        assert result["recorded"] is True
        assert result["windowStatus"] == "documented"
        assert result["capture"]["achievedMargin"] == pytest.approx(0.75)
        assert result["capture"]["captureLatencySeconds"] == 21600.0
        assert result["capture"]["unavailable"] == ["prompt-transcript"]
        assert result["meetsMarginTarget"] is True
        assert result["marginTarget"] == 0.5
        assert result["expired"] == []

    def test_capture_evidence_rpc_unknown_window_is_honest(self, server):
        response = call(
            server,
            "observe/captureEvidence",
            {
                "vendor": "claude",
                "source": "local-session-transcripts",
                "evidenceTime": T0.isoformat(),
            },
        )
        result = response["result"]
        assert result["windowStatus"] == "unknown"
        assert result["capture"]["achievedMargin"] is None
        assert result["meetsMarginTarget"] is False
        assert result["window"]["documented"] is False

    def test_capture_evidence_rpc_rejects_bad_timestamps(self, server):
        response = call(
            server,
            "observe/captureEvidence",
            {
                "vendor": "copilot",
                "source": "agent-session-logs",
                "evidenceTime": "not-a-time",
            },
        )
        assert "error" in response

    def test_expired_capture_marks_health_and_sessions_within_one_session(
        self, server
    ):
        # AC-47's end-to-end shape: a capture whose window has closed marks
        # itself, observe/health names the closed window, and
        # observe/sessions carries the marker in its warnings — the gap is
        # never presented as an absence of activity.
        response = call(
            server,
            "observe/captureEvidence",
            {
                "vendor": "copilot",
                "source": "agent-session-logs",
                "evidenceTime": T0.isoformat(),
                "capturedAt": (T0 + timedelta(days=2)).isoformat(),
            },
        )
        expired = response["result"]["expired"]
        assert len(expired) == 1
        assert expired[0]["marker"] == "evidence_expired"
        assert expired[0]["windowLabel"] == "copilot agent-session-logs (1 day)"

        health = call(server, "observe/health", {})["result"]
        assert len(health["evidenceExpired"]) == 1
        assert (
            health["evidenceExpired"][0]["windowLabel"]
            == "copilot agent-session-logs (1 day)"
        )

        sessions = call(server, "observe/sessions", {})["result"]
        assert any(
            "evidence_expired" in warning and "copilot agent-session-logs (1 day)" in warning
            for warning in sessions["warnings"]
        )

        # Sticky for the session: a second health call still reports it.
        health_again = call(server, "observe/health", {})["result"]
        assert len(health_again["evidenceExpired"]) == 1

    def test_trust_metric_envelope_names_the_expired_window(self, server):
        call(
            server,
            "observe/captureEvidence",
            {
                "vendor": "copilot",
                "source": "agent-session-logs",
                "evidenceTime": T0.isoformat(),
                "capturedAt": (T0 + timedelta(days=2)).isoformat(),
            },
        )
        server.ledger.append(
            {
                "story_id": "s1",
                "phase": "build",
                "loop_id": "loop",
                "loop_iteration": 1,
                "actor_id": "agent",
                "actor_version": "1",
                "actor_kind": "external",
                "policy_version": "p",
                "action_type": "diff",
            }
        )
        result = call(server, "trust/rejectionRate", {})["result"]
        gap_classes = [gap["gapClass"] for gap in result["coverage"]["gaps"]]
        assert "evidence_expired" in gap_classes
