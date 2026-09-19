"""Per-figure statistical disclosure (FR-M41-14; N1 Workstream C task 14).

Every figure carries its sample count, a confidence interval where the
statistic admits one (Wilson on proportions), and the missing-data share.
An empty sample reads ``insufficient_evidence`` — never zero. A statistic
with no admissible CI says so explicitly (``ciReason``), never by
omission.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics.compare import compute_agent_comparison
from meridian_core.metrics.reasons import compute_reason_distribution
from meridian_core.metrics.statistics import (
    figure_statistics,
    proportion_statistics,
    wilson_interval,
)
from meridian_core.metrics.trust import compute_rejection_rate


class TestWilsonInterval:
    def test_known_value_centre_of_distribution(self):
        # 50/100 at z=1.959964: Wilson = (0.40383, 0.59617).
        low, high = wilson_interval(50, 100)
        assert low == pytest.approx(0.40383, abs=1e-4)
        assert high == pytest.approx(0.59617, abs=1e-4)
        assert 0.0 <= low < 0.5 < high <= 1.0

    def test_edges_are_bounded_not_degenerate(self):
        # 0/3: the point estimate is 0 but the interval is not — an edge
        # proportion keeps an honest upper bound.
        low, high = wilson_interval(0, 3)
        assert low == 0.0
        assert 0.0 < high < 1.0
        low, high = wilson_interval(3, 3)
        assert 0.0 < low < 1.0
        assert high == 1.0

    def test_empty_sample_has_no_interval(self):
        with pytest.raises(ValueError):
            wilson_interval(0, 0)

    def test_successes_clamped_into_range(self):
        low, high = wilson_interval(7, 5)
        assert low == pytest.approx(wilson_interval(5, 5)[0])


class TestProportionStatistics:
    def test_carries_sample_count_ci_and_missing_share(self):
        stats = proportion_statistics(8, 10, missing=2, available=10)
        assert stats["status"] == "ok"
        assert stats["sampleCount"] == 10
        assert stats["missingShare"] == 0.2
        assert stats["confidenceInterval"]["method"] == "wilson"
        assert stats["confidenceInterval"]["level"] == 0.95
        low = stats["confidenceInterval"]["low"]
        high = stats["confidenceInterval"]["high"]
        assert 0.0 <= low <= 0.8 <= high <= 1.0

    def test_empty_sample_reads_insufficient_evidence_never_zero(self):
        stats = proportion_statistics(0, 0)
        assert stats["status"] == "insufficient_evidence"
        assert stats["sampleCount"] == 0
        assert stats["confidenceInterval"] is None
        assert "insufficient_evidence" in stats["ciReason"]

    def test_missing_share_clamped_to_population(self):
        stats = proportion_statistics(1, 1, missing=50, available=1)
        assert stats["missingShare"] == 1.0


class TestNoCiStatistics:
    def test_explicit_no_ci_reason_for_unmodelled_statistics(self):
        stats = figure_statistics(12, statistic="median lead time")
        assert stats["status"] == "ok"
        assert stats["sampleCount"] == 12
        assert stats["confidenceInterval"] is None
        assert stats["ciReason"].startswith("no_confidence_interval")
        assert "median lead time" in stats["ciReason"]

    def test_empty_unmodelled_sample_reads_insufficient_evidence(self):
        stats = figure_statistics(0, statistic="median lead time")
        assert stats["status"] == "insufficient_evidence"
        assert stats["confidenceInterval"] is None


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _diff_entry(story: str, actor: str, seq_note: int = 0):
    return {
        "story_id": story,
        "phase": "build",
        "loop_id": "L",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }


def _rejection_entry(rejected_sequence, story: str):
    return {
        **_diff_entry(story, "reviewer-human"),
        "action_type": "rejection",
        "phase": "review",
        "decision": "rejected",
        "rework_reason": "missing-tests",
        "rejected_sequence": rejected_sequence,
    }


class TestTrustFiguresCarryStatistics:
    def test_rejection_rate_figure_has_wilson_interval(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            for index in range(4):
                ledger.append(_diff_entry("s1", "agent-a", index))
            ledger.append(_rejection_entry(2, "s1"))
            result = compute_rejection_rate(ledger)
        finally:
            ledger.close()
        stats = result["statistics"]
        assert stats["sampleCount"] == 4
        assert stats["confidenceInterval"]["method"] == "wilson"
        # rate 0.25 must sit inside its own interval.
        assert (
            stats["confidenceInterval"]["low"]
            <= 0.25
            <= stats["confidenceInterval"]["high"]
        )
        # The agent-authored population is fully attributed: no missing.
        assert stats["missingShare"] == 0.0

    def test_rejection_rate_missing_share_counts_unattributed(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            # An external observation with direct confidence carries no
            # positive authorship evidence -> unattributed is missing
            # authorship evidence (FR-M41-04), half the sample here.
            ledger.append(
                {
                    **_diff_entry("s1", "human-dev"),
                    "actor_kind": "external",
                }
            )
            result = compute_rejection_rate(ledger)
        finally:
            ledger.close()
        assert result["statistics"]["missingShare"] == 0.5

    def test_empty_ledger_statistics_read_insufficient_evidence(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            result = compute_rejection_rate(ledger)
        finally:
            ledger.close()
        assert result["statistics"]["status"] == "insufficient_evidence"
        assert result["statistics"]["confidenceInterval"] is None
        assert result["statistics"]["sampleCount"] == 0

    def test_yield_figure_has_wilson_interval(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            ledger.append(_rejection_entry(2, "s1"))
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        yield_a = result["agents"]["agent-a"]["yield"]
        assert yield_a["value"] == 1.0
        assert yield_a["statistics"]["sampleCount"] == 1
        assert yield_a["statistics"]["confidenceInterval"]["method"] == "wilson"
        yield_b = result["agents"]["agent-b"]["yield"]
        # 0/1 yield: point estimate 0, honest upper bound below 1.
        assert yield_b["value"] == 0.0
        assert 0.0 < yield_b["statistics"]["confidenceInterval"]["high"] < 1.0

    def test_yield_without_proposals_reads_insufficient_evidence(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(
                ledger, story_id="s1", actor_ids=["agent-a", "ghost"]
            )
        finally:
            ledger.close()
        stats = result["agents"]["ghost"]["yield"]["statistics"]
        assert stats["status"] == "insufficient_evidence"
        assert stats["confidenceInterval"] is None

    def test_reason_distribution_states_no_admissible_ci(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_rejection_entry(None, "s1"))
            result = compute_reason_distribution(ledger)
        finally:
            ledger.close()
        stats = result["statistics"]
        assert stats["status"] == "ok"
        assert stats["sampleCount"] == 1
        # A class distribution is not one proportion: the figure SAYS the
        # CI is not admissible — explicit, never an omission.
        assert stats["confidenceInterval"] is None
        assert stats["ciReason"].startswith("no_confidence_interval")
