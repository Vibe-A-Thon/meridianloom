"""The coverage envelope and cursor pagination (FR-M41-07/08/09,
NFR-33/34; N1 Workstream A, D36 — G-01 fix).

Unit level: the envelope's derived semantics, scan_scope's cursor walk,
ledger.query's after_sequence pagination, and the FR-M41-09 module-level
rule that a derived projection is disabled over a truncated population
(the honest-local behaviour the spend forecast now consumes via the
envelope instead of detecting a 1,000-row cap of its own). The 50,000-
entry performance + full-scan-equality proof (AC-41, NFR-33) lives in
test_full_history_metrics.py.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import (
    CoverageEnvelope,
    compute_reason_distribution,
    compute_rejection_rate,
    envelope_for,
    forbid_projection,
    forecast_monthly_spend,
    scan_scope,
)

DIFF = "diff"


def _entry(story: str, actor: str, action_type: str = DIFF, **extra):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": action_type,
    }
    entry.update(extra)
    return entry


@pytest.fixture()
def ledger(tmp_path: Path):
    ledger = Ledger(
        tmp_path / "ledger",
        EphemeralSigningKeyProvider(),
        verify_on_open=False,
    )
    yield ledger
    ledger.close()


class TestQueryCursorPagination:
    """FR-M41-07: after_sequence is an exclusive cursor keyed on the
    gapless seq; pages reassemble the full stream; limit stays a page
    size, never the only bound."""

    def _seed(self, ledger: Ledger, n: int) -> None:
        for i in range(n):
            ledger.append(_entry(f"S{i % 3}", f"agent-{i % 2}"))

    def test_pages_reassemble_full_history(self, ledger):
        self._seed(ledger, 25)
        pages = []
        after = None
        while True:
            page = ledger.query(after_sequence=after, limit=10)
            if not page:
                break
            pages.append(page)
            after = page[-1]["seq"]
        rows = [row for page in pages for row in page]
        assert [row["seq"] for row in rows] == list(range(1, 26))
        assert [len(page) for page in pages] == [10, 10, 5]

    def test_after_sequence_is_exclusive_and_composable_with_filters(self, ledger):
        self._seed(ledger, 20)
        page1 = ledger.query(actor_id="agent-0", limit=3)
        page2 = ledger.query(
            actor_id="agent-0", after_sequence=page1[-1]["seq"], limit=3
        )
        assert [row["seq"] for row in page1] == [1, 3, 5]
        assert [row["seq"] for row in page2] == [7, 9, 11]

    def test_count_matches_query_scope(self, ledger):
        self._seed(ledger, 20)
        assert ledger.count() == 20
        assert ledger.count(actor_id="agent-1") == 10
        assert ledger.count(from_sequence=5, to_sequence=9) == 5

    def test_page_size_clamp_is_a_page_size_not_a_cap(self, ledger):
        # FR-M41-07: the 1,000 clamp survives only as the DEFAULT page
        # size — the cursor reaches past it.
        self._seed(ledger, 5)
        assert len(ledger.query(limit=10_000)) == 5  # clamped page, short ledger
        many = Ledger(
            ledger.dir.parent / "many",
            EphemeralSigningKeyProvider(),
            verify_on_open=False,
        )
        try:
            for i in range(1500):
                many.append(_entry(f"S{i % 3}", f"agent-{i % 2}"))
            assert len(many.query(limit=10_000)) == 1000  # one full page
            rest = many.query(after_sequence=1000, limit=10_000)
            assert [row["seq"] for row in rest] == list(range(1001, 1501))
        finally:
            many.close()


class TestScanScope:
    def test_full_walk_reports_rows_and_available(self, ledger):
        for i in range(7):
            ledger.append(_entry(f"S{i % 2}", "agent-one", action_type=DIFF))
        ledger.append(_entry("SX", "agent-two", action_type="test_run"))
        rows, available = scan_scope(ledger, action_type=DIFF, page_size=3)
        assert available == 7
        assert len(rows) == 7
        assert [row["seq"] for row in rows] == list(range(1, 8))

    def test_small_page_size_still_walks_everything(self, ledger):
        for i in range(50):
            ledger.append(_entry(f"S{i % 5}", "agent-one"))
        rows, available = scan_scope(ledger, page_size=7)
        assert available == 50 and len(rows) == 50


class TestCoverageEnvelope:
    def test_complete_population(self, ledger):
        for i in range(4):
            ledger.append(_entry(f"S{i}", "agent-one"))
        rows, available = scan_scope(ledger)
        envelope = envelope_for(0.5, rows, available)
        assert envelope.truncated is False
        assert envelope.rowsConsidered == 4
        assert envelope.rowsAvailable == 4
        assert envelope.coverage == 1.0
        assert envelope.label == "complete"
        assert envelope.sequenceRange == (1, 4)
        assert envelope.to_dict() == {
            "value": 0.5,
            "rowsConsidered": 4,
            "rowsAvailable": 4,
            "truncated": False,
            "sequenceRange": [1, 4],
            "coverage": 1.0,
            "label": "complete",
        }

    def test_truncated_population_is_derived_never_supplied(self):
        rows = [{"seq": n} for n in range(1, 4)]
        envelope = envelope_for(0.5, rows, 10)
        assert envelope.truncated is True
        assert envelope.rowsConsidered == 3
        assert envelope.rowsAvailable == 10
        assert envelope.coverage == 0.3
        assert envelope.label == "partial"
        assert envelope.sequenceRange == (1, 3)

    def test_short_auxiliary_scan_truncates_the_figure(self):
        # G-01's exact shape: a complete primary population but the
        # rejection lookup capped — the figure is still truncated.
        primary = [{"seq": n} for n in range(1, 11)]
        envelope = envelope_for(0.5, primary, 10, aux_scans=((primary[:3], 10),))
        assert envelope.truncated is True
        assert envelope.label == "partial"

    def test_empty_population_reads_empty_not_zero(self):
        envelope = envelope_for(None, [], 0)
        assert envelope.truncated is False
        assert envelope.label == "empty"
        assert envelope.sequenceRange == (None, None)
        assert envelope.coverage == 1.0

    def test_declared_window_is_the_available_population(self, ledger):
        # from_sequence/to_sequence is a declared scope: rows inside the
        # window with nothing missed are complete, never "truncated".
        for i in range(10):
            ledger.append(_entry(f"S{i}", "agent-one"))
        rows, available = scan_scope(ledger, from_sequence=3, to_sequence=6)
        envelope = envelope_for(1.0, rows, available)
        assert available == 4
        assert envelope.truncated is False
        assert envelope.sequenceRange == (3, 6)
        assert envelope.label == "complete"


class TestProjectionDisabledWhenTruncated:
    """FR-M41-09 at the module level: the forecast consumes the envelope
    — a deliberately truncated population disables the projection with
    the reason in text (the AC-41 'displayed and disabled' tail)."""

    def _truncated_envelope(self) -> CoverageEnvelope:
        return envelope_for(
            None, [{"seq": n} for n in range(1, 101)], 10_000
        )

    def test_forbid_projection_reason(self):
        reason = forbid_projection(self._truncated_envelope())
        assert reason is not None
        assert "projection disabled" in reason
        assert "FR-M41-09" in reason

    def test_forbid_projection_passes_complete_envelopes(self, ledger):
        for _ in range(3):
            ledger.append(_entry("S", "agent-one"))
        rows, available = scan_scope(ledger)
        assert forbid_projection(envelope_for(None, rows, available)) is None

    def test_forecast_disabled_over_truncated_scope(self):
        forecast = forecast_monthly_spend(
            {"2026-01": 10.0, "2026-02": 20.0, "2026-03": 30.0},
            "2026-04",
            coverage_envelope=self._truncated_envelope(),
        )
        assert forecast["status"] == "truncated"
        assert forecast["projectedUsd"] is None
        assert forecast["slopeUsdPerMonth"] is None
        assert "projection disabled" in forecast["note"]

    def test_forecast_unchanged_without_envelope(self):
        forecast = forecast_monthly_spend(
            {"2026-01": 10.0, "2026-02": 20.0, "2026-03": 30.0}, "2026-04"
        )
        assert forecast["status"] == "ok"
        assert forecast["projectedUsd"] is not None


class TestMetricsCarryTheEnvelope:
    """Every migrated metric returns the envelope in the same operation
    as the figure (NFR-34)."""

    def test_rejection_rate_result_shape(self, ledger):
        seq = ledger.append(_entry("S1", "agent-one")).sequence
        ledger.append(
            _entry(
                "S1",
                "unknown",
                action_type="rejection",
                rejected_sequence=seq,
                decision="rejected",
            )
        )
        result = compute_rejection_rate(ledger)
        envelope = result["coverage"]
        assert envelope["truncated"] is False
        assert envelope["rowsConsidered"] == 2
        assert envelope["rowsAvailable"] == 2
        assert envelope["value"] == result["rate"]
        assert envelope["label"] == "complete"

    def test_reason_distribution_result_shape(self, ledger):
        seq = ledger.append(_entry("S1", "agent-one")).sequence
        ledger.append(
            _entry(
                "S1",
                "unknown",
                action_type="rejection",
                rejected_sequence=seq,
                decision="rejected",
                rework_reason="missing-tests",
            )
        )
        result = compute_reason_distribution(ledger)
        envelope = result["coverage"]
        assert envelope["rowsConsidered"] == 1
        assert envelope["value"] == 1  # the headline total
        assert envelope["truncated"] is False

    def test_envelope_survives_json_round_trip(self, ledger):
        ledger.append(_entry("S1", "agent-one"))
        import json

        result = compute_rejection_rate(ledger)
        assert json.loads(json.dumps(result))["coverage"]["label"] == "complete"


class TestCoverageDisclosureLatency:
    """NFR-34: the disclosure is computed in the same operation — the
    envelope must not add a second scan's worth of latency. Measured,
    with a generous floor (the marker is registered in pyproject)."""

    @pytest.mark.perf
    def test_scan_scope_over_5000_rows_stays_under_budget(self, ledger):
        for i in range(5000):
            ledger.append(_entry(f"S{i % 10}", f"agent-{i % 3}"))
        started = time.perf_counter()
        rows, available = scan_scope(ledger)
        elapsed = time.perf_counter() - started
        print(
            f"\nNFR-34/33: scan_scope over 5,000 rows took "
            f"{elapsed * 1000:.0f} ms (budget 5,000 ms)"
        )
        assert available == 5000 and len(rows) == 5000
        assert elapsed < 5.0
