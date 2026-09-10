"""F2's gate, and everything it refuses to say.

The measures are the easy part. What makes this gate worth having is that it
returns `insufficient_evidence` when the evidence is insufficient, reports
`unavailable` where nothing was recorded, and never substitutes a zero for an
absence — because the decision on the other side of it is whether to start
building the Orchestra, and a GO on a five-story sample is the most expensive
thing this codebase could get wrong.
"""

from __future__ import annotations

import pytest

from meridian_core.metrics.evidence_gate import (
    GO,
    INSUFFICIENT,
    OK,
    PIVOT,
    REQUIRED_STORIES,
    STOP,
    UNAVAILABLE,
    compute_evidence_gate,
)


class FakeLedger:
    """The rows the gate reads, without a database in the way."""

    def __init__(self, rows: list[dict]):
        self._rows = [dict(row, seq=index + 1) for index, row in enumerate(rows)]
        self.last_sequence = len(self._rows)

    def count(self, **filters) -> int:
        return len(self._match(filters))

    def query(self, *, after_sequence=None, limit=1000, **filters):
        rows = self._match(filters)
        if after_sequence is not None:
            rows = [row for row in rows if row["seq"] > after_sequence]
        return rows[:limit]

    def _match(self, filters: dict) -> list[dict]:
        rows = self._rows
        for key, value in filters.items():
            if value is None or key in {"after_sequence", "limit"}:
                continue
            column = {
                "action_type": "action_type",
                "story_id": "story_id",
                "actor_id": "actor_id",
            }.get(key)
            if column:
                rows = [row for row in rows if row.get(column) == value]
            elif key == "from_sequence":
                rows = [row for row in rows if row["seq"] >= value]
            elif key == "to_sequence":
                rows = [row for row in rows if row["seq"] <= value]
        return rows


def diff(story: str, decision: str = "proposed", ts: str = "2026-09-01T10:00:00+00:00"):
    return {
        "action_type": "diff",
        "story_id": story,
        "decision": decision,
        "ts_utc": ts,
    }


def gate(story: str, decision: str = "pass", ts: str = "2026-09-01T10:00:00+00:00"):
    return {
        "action_type": "gate",
        "story_id": story,
        "subject": story,
        "decision": decision,
        "ts_utc": ts,
    }


def rejection(story: str, target_seq: int, tool_calls: str = ""):
    return {
        "action_type": "rejection",
        "story_id": story,
        "rejected_sequence": target_seq,
        "tool_calls": tool_calls,
        "ts_utc": "2026-09-01T11:00:00+00:00",
    }


def approval(story: str, ts: str = "2026-09-01T10:30:00+00:00"):
    return {
        "action_type": "approval",
        "story_id": story,
        "subject": story,
        "ts_utc": ts,
    }


# --- the refusals ---------------------------------------------------------


class TestItRefusesToOverclaim:
    def test_fewer_than_twenty_stories_is_no_answer_at_all(self):
        rows = []
        for index in range(5):
            rows += [diff(f"S{index}"), gate(f"S{index}")]
        report = compute_evidence_gate(FakeLedger(rows))
        assert report["recommendation"]["verdict"] == INSUFFICIENT
        assert "5 of 20" in report["recommendation"]["reasons"][0]
        assert report["stories"]["required"] == REQUIRED_STORIES

    def test_the_two_unrecordable_measures_say_so_rather_than_reading_zero(self):
        report = compute_evidence_gate(FakeLedger([diff("S1")]))
        for name in ("provenanceQueriesRun", "firstValueRetention"):
            measure = report["measures"][name]
            assert measure["status"] == UNAVAILABLE
            # The distinction that matters: absent evidence, not a zero result.
            assert measure["value"] is None
            assert len(measure["note"]) > 40

    def test_no_role_pack_is_not_a_clean_bill_of_health(self):
        rows = [approval("S1"), gate("S1")]
        report = compute_evidence_gate(FakeLedger(rows), hygiene=None)
        hygiene = report["measures"]["approvalHygiene"]
        assert hygiene["status"] == UNAVAILABLE
        assert "not a clean bill of health" in hygiene["note"]

    def test_no_supplied_baseline_means_no_change_failure_comparison(self):
        rows = [diff("S1", "approved"), gate("S1")]
        report = compute_evidence_gate(FakeLedger(rows))
        failure = report["measures"]["changeFailureRate"]
        assert failure["status"] == UNAVAILABLE
        # It still reports what it measured, it just will not call it a verdict.
        assert failure["observed"] is not None
        assert "cannot know" in failure["note"]

    def test_a_run_that_exercised_nothing_cannot_decide(self):
        # Twenty stories, but no gates, no approvals, nothing to compare.
        rows = [diff(f"S{index}") for index in range(REQUIRED_STORIES)]
        report = compute_evidence_gate(FakeLedger(rows))
        assert report["recommendation"]["verdict"] == INSUFFICIENT
        assert "did not exercise the governance layer" in " ".join(
            report["recommendation"]["reasons"]
        )


# --- the verdicts ---------------------------------------------------------


def _twenty(gated_rejects: int, ungated_rejects: int) -> list[dict]:
    """Ten gated and ten ungated stories, with the rejections you ask for."""
    rows: list[dict] = []
    for index in range(10):
        rows.append(gate(f"G{index}"))
        rows.append(approval(f"G{index}"))
        rows.append(diff(f"G{index}", "approved"))
    for index in range(10):
        rows.append(diff(f"U{index}", "approved"))

    ledger = FakeLedger(rows)
    diffs_gated = [r for r in ledger._rows if r["action_type"] == "diff" and r["story_id"].startswith("G")]
    diffs_ungated = [r for r in ledger._rows if r["action_type"] == "diff" and r["story_id"].startswith("U")]
    for row in diffs_gated[:gated_rejects]:
        rows.append(rejection(row["story_id"], row["seq"]))
    for row in diffs_ungated[:ungated_rejects]:
        rows.append(rejection(row["story_id"], row["seq"]))
    return rows


class TestTheVerdict:
    def test_go_when_gating_reduced_rejection_and_stability_held(self):
        # Gated stories reject less than ungated ones: the core claim, evidenced.
        report = compute_evidence_gate(
            FakeLedger(_twenty(gated_rejects=1, ungated_rejects=6)),
            baseline_change_failure_rate=0.5,
            hygiene=lambda subject: [],
        )
        assert report["recommendation"]["verdict"] == GO
        assert report["measures"]["rejectionRate"]["status"] == OK
        assert report["measures"]["rejectionRate"]["value"] < 0

    def test_go_still_flags_that_query_usage_is_unevidenced(self):
        report = compute_evidence_gate(
            FakeLedger(_twenty(gated_rejects=1, ungated_rejects=6)),
            baseline_change_failure_rate=0.5,
            hygiene=lambda subject: [],
        )
        # §F2 requires provenance queries to be run for a GO, and that cannot
        # be evidenced. A GO that hid the gap would be the same lie in a
        # better mood.
        assert any(
            "NOT evidenced" in reason
            for reason in report["recommendation"]["reasons"]
        )

    def test_gating_that_changed_nothing_is_ceremony(self):
        # Identical rejection either side, and no gate ever blocked anything.
        report = compute_evidence_gate(
            FakeLedger(_twenty(gated_rejects=5, ungated_rejects=5)),
            baseline_change_failure_rate=0.5,
            hygiene=lambda subject: [],
        )
        assert report["recommendation"]["verdict"] in {STOP, PIVOT}
        assert "ceremony" in " ".join(report["recommendation"]["reasons"])

    def test_stop_is_reported_as_a_success_path(self):
        report = compute_evidence_gate(
            FakeLedger(_twenty(gated_rejects=5, ungated_rejects=5)),
            baseline_change_failure_rate=0.5,
            hygiene=lambda subject: [],
        )
        assert "Ship the Flight Recorder" in " ".join(
            report["recommendation"]["reasons"]
        )


# --- the measures themselves ----------------------------------------------


class TestMeasures:
    def test_gate_catches_count_blocked_evaluations(self):
        rows = [gate("S1", "block"), gate("S2", "pass"), gate("S3", "block")]
        report = compute_evidence_gate(FakeLedger(rows))
        catches = report["measures"]["gateCatches"]
        assert catches["status"] == OK
        assert catches["value"] == 2
        assert catches["gatesRun"] == 3

    def test_time_cost_is_gate_to_approval_in_seconds(self):
        rows = [
            gate("S1", ts="2026-09-01T10:00:00+00:00"),
            approval("S1", ts="2026-09-01T10:30:00+00:00"),
        ]
        report = compute_evidence_gate(FakeLedger(rows))
        cost = report["measures"]["timeCostPerGatedChange"]
        assert cost["status"] == OK
        assert cost["value"] == pytest.approx(1800.0)
        assert cost["unit"] == "seconds"

    def test_hygiene_warnings_are_surfaced_not_summarised_away(self):
        rows = [gate("S1"), approval("S1")]
        report = compute_evidence_gate(
            FakeLedger(rows),
            hygiene=lambda subject: [f"{subject} approved 4 seconds after ingest"],
        )
        hygiene = report["measures"]["approvalHygiene"]
        assert hygiene["status"] == OK
        assert hygiene["value"] == 1
        assert "4 seconds" in hygiene["warnings"][0]

    def test_the_report_carries_its_coverage_envelope(self):
        report = compute_evidence_gate(FakeLedger([diff("S1")]))
        assert "coverage" in report
        assert report["coverage"]["rowsConsidered"] == 1
