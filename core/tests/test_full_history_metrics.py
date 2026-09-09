"""Full-history correctness at 50,000 entries (NFR-33, AC-41; N1
Workstream A — G-01 fix, D36).

AC-41: a ledger of 50,000 entries is built; every trust and spend metric
is computed and each result (a) completes within the documented budget —
NFR-33's floor: each metric under 5 s on this machine, the measured rate
printed per metric — and (b) equals an INDEPENDENT full-scan
recomputation over the same 50k, where "independent" means raw SQL over
``ledger.conn`` plus counting code written here, never the metrics
modules' own query path. Every result must also carry the FR-M41-08
envelope with rowsConsidered / rowsAvailable / truncated / sequenceRange,
computed in the same operation (NFR-34).

The fixture is built programmatically (fast synthetic appends — nothing
committed); durability is NOT under test here (test_ledger_durability
owns FR-M10-08), so the build relaxes synchronous=OFF for speed.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import (
    compute_agent_comparison,
    compute_dora_metrics,
    compute_jcurve,
    compute_reason_distribution,
    compute_rejection_rate,
    compute_trust_score,
    forecast_monthly_spend,
    monthly_spend_totals,
    scan_scope,
    spend_by_dimension,
)
from meridian_core.server import SidecarServer

N_ENTRIES = 50_000
N_DIFFS = 40_000
N_REJECTIONS = 5_000
N_TEST_RUNS = 5_000

AGENTS = ("agent-one", "agent-two", "agent-three")
REASONS = ("wrong-requirement", "incorrect-implementation", "missing-tests")
BASE = datetime(2025, 6, 1, tzinfo=timezone.utc)
ADOPTION = "2025-12-01T00:00:00Z"

#: NFR-33 documented budget: each metric completes a 50,000-entry
#: full-history derivation well under this on reference-class hardware.
BUDGET_SECONDS = 5.0


def _diff_entry(i: int) -> dict:
    entry = {
        "story_id": f"STORY-{i % 20:02d}",
        "phase": "build",
        "loop_id": "L1",
        "loop_iteration": 1,
        "actor_id": AGENTS[i % 3],
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        # Stories 01/05/09/13/17 open with a rejected first diff so the
        # DORA lead-time key has real evidence; story 13 stays all-
        # rejected (a story whose changes never passed review).
        "decision": (
            "rejected"
            if (i < 20 and i % 4 == 1) or i % 10 == 3
            else ("reworked" if i % 10 == 6 else "approved")
        ),
        "repo_id": "repo-b" if i % 17 == 0 else "repo-a",
        "ts_utc": (BASE + timedelta(seconds=i * 800)).isoformat().replace("+00:00", "Z"),
    }
    if i % 5 != 0:
        entry["confidence"] = round(0.30 + (i % 40) * 0.01, 6)
    if i % 2 == 0:
        entry["tokens_in"] = 1000 + i % 7
        entry["tokens_out"] = 500 + i % 5
        entry["cost_usd"] = round(0.01 * (1 + i % 9), 6)
    return entry


def _rejection_entry(k: int) -> dict:
    target = 6 + k * 8  # a diff sequence, 6..39998
    i = target - 1
    entry = {
        "story_id": f"STORY-{i % 20:02d}",
        "phase": "review",
        "loop_id": "rejection",
        "loop_iteration": 0,
        "actor_id": "reviewer-one",
        "actor_version": "1.0.0",
        "actor_kind": "external",
        "policy_version": "policy-v1",
        "action_type": "rejection",
        "decision": "rejected",
        "rejected_sequence": None if k % 9 == 0 else target,
        "repo_id": "repo-a",
        "ts_utc": (BASE + timedelta(seconds=i * 800 + 3600))
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if k % 7 != 0:
        entry["rework_reason"] = REASONS[k % 3]
    if k % 11 == 0:
        entry["tool_calls"] = json.dumps([{"shape": "reverted"}])
    return entry


def _test_run_entry(j: int) -> dict:
    entry = {
        "story_id": f"STORY-{j % 20:02d}",
        "phase": "verify",
        "loop_id": "L1",
        "loop_iteration": 2,
        "actor_id": AGENTS[j % 3],
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "test_run",
        "decision": "rejected" if j % 4 == 0 else "approved",
        "repo_id": "repo-a",
        "ts_utc": (BASE + timedelta(seconds=32_100_000 + j * 700))
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if j % 2 == 1:
        entry["tokens_in"] = 300 + j % 13
        entry["tokens_out"] = 100 + j % 7
        entry["cost_usd"] = round(0.02 * (1 + j % 4), 6)
    return entry


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """The AC-41 ledger: 50,000 deterministic synthetic entries."""
    tmp = tmp_path_factory.mktemp("big-ledger")
    ledger = Ledger(
        tmp / "ledger",
        EphemeralSigningKeyProvider(),
        verify_on_open=False,
        tree_head_interval=1_000_000,  # tree heads are not under test
    )
    # Durability is test_ledger_durability's job; here the build would
    # otherwise spend ~1.3 ms/entry on fsync alone.
    ledger.conn.execute("PRAGMA synchronous = OFF")
    started = time.perf_counter()
    for i in range(N_DIFFS):
        ledger.append(_diff_entry(i))
    for k in range(N_REJECTIONS):
        ledger.append(_rejection_entry(k))
    for j in range(N_TEST_RUNS):
        ledger.append(_test_run_entry(j))
    build_s = time.perf_counter() - started
    assert ledger.last_sequence == N_ENTRIES
    print(f"\nAC-41 fixture: {N_ENTRIES} entries appended in {build_s:.1f}s")
    yield ledger
    ledger.close()


def _raw(ledger, sql, args=()):
    """The independent oracle path: raw SQL, no metric modules."""
    return ledger.conn.execute(sql, args).fetchall()


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _week_monday(day: date) -> date:
    return day.fromordinal(day.toordinal() - day.weekday())


def _linked_sequences(ledger) -> set[int]:
    return {
        row[0]
        for row in _raw(
            ledger,
            "SELECT rejected_sequence FROM ledger_entry"
            " WHERE action_type='rejection' AND rejected_sequence IS NOT NULL",
        )
    }


def _reverted_sequences(ledger) -> set[int]:
    return {
        row[0]
        for row in _raw(
            ledger,
            "SELECT rejected_sequence FROM ledger_entry"
            " WHERE action_type='rejection' AND rejected_sequence IS NOT NULL"
            " AND tool_calls LIKE '%\"reverted\"%'",
        )
    }


# These tests assert two different things about the same call: that the result
# equals a full-scan recomputation (AC-41 correctness, which holds on any
# machine) and that it lands inside the NFR-33 budget (which does not, on a
# machine running three other suites). Conflating them means a busy CI runner
# reports a correctness failure, and a real regression looks like noise.
#
# So the measurement is always taken and always printed; the budget is enforced
# unless the runner says it is sharing the machine. CI enforces it in a
# dedicated job on a fresh runner, and a developer running the suite locally
# enforces it by default — the stale PASS this budget suffered happened
# precisely because nobody saw the number.
_REPORT_ONLY = os.environ.get("MERIDIAN_PERF_REPORT_ONLY") == "1"


def _timed(label: str, fn):
    started = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - started
    rate = N_ENTRIES / elapsed if elapsed else float("inf")
    verdict = (
        "reported only (shared runner)"
        if _REPORT_ONLY
        else f"budget {BUDGET_SECONDS:.0f}s"
    )
    print(
        f"NFR-33 {label}: {elapsed * 1000:.0f} ms over 50k "
        f"({rate:,.0f} rows/s; {verdict})"
    )
    if not _REPORT_ONLY:
        assert elapsed < BUDGET_SECONDS, f"{label} over budget: {elapsed:.2f}s"
    return result


def _assert_complete_envelope(envelope, value=None, available=N_ENTRIES,
                              sequence_range=(1, N_ENTRIES)):
    assert envelope["truncated"] is False
    assert envelope["rowsAvailable"] == available
    assert envelope["rowsConsidered"] == available
    assert envelope["coverage"] == 1.0
    assert envelope["label"] == "complete"
    assert envelope["sequenceRange"] == list(sequence_range)
    if value is not None:
        assert envelope["value"] == value


class TestRejectionRateAt50k:
    def test_equals_full_scan_recomputation(self, big):
        result = _timed(
            "trust/rejectionRate",
            lambda: compute_rejection_rate(big),
        )
        linked = _linked_sequences(big)
        # The F0 headline counts the linked-rejection shape only (a
        # decision of rejected|reworked enters the FR-M37-01 by* views,
        # not the headline rate — that is the metric's contract).
        proposed, rejected = 0, 0
        for (seq, decision) in _raw(
            big, "SELECT seq, decision FROM ledger_entry WHERE action_type='diff'"
        ):
            proposed += 1
            if seq in linked:
                rejected += 1
        assert proposed == N_DIFFS
        assert result["proposed"] == proposed
        assert result["rejected"] == rejected
        assert result["rate"] == round(rejected / proposed, 6)
        _assert_complete_envelope(result["coverage"], value=result["rate"])


class TestTrustScoreAt50k:
    def test_equals_full_scan_recomputation(self, big):
        actor = "agent-one"
        result = _timed(
            "trust/score",
            lambda: compute_trust_score(big, actor_id=actor),
        )
        rows = _raw(
            big,
            "SELECT seq, story_id, decision, confidence FROM ledger_entry"
            " WHERE action_type='diff' AND actor_id=?",
            (actor,),
        )
        linked = _linked_sequences(big)
        reverted = _reverted_sequences(big)

        def is_rejected(seq, decision):
            return seq in linked or decision in ("rejected", "reworked")

        proposed = len(rows)
        rejected = sum(1 for seq, _, d, _ in rows if is_rejected(seq, d))
        rate = round(rejected / proposed, 6)
        fpy = round(1 - rate, 6)
        confident = [
            (confidence, 0.0 if is_rejected(seq, d) else 1.0)
            for seq, _, d, confidence in rows
            if confidence is not None
        ]
        calibration = round(
            sum(abs(c - o) for c, o in confident) / len(confident), 6
        )
        approved = [(seq, d) for seq, _, d, _ in rows if d == "approved"]
        revert_rate = round(
            sum(1 for seq, _ in approved if seq in reverted) / len(approved), 6
        )
        weighted = (
            0.30 * fpy
            + 0.25 * (1 - rate)
            + 0.20 * (1 - calibration)
            + 0.15 * (1 - revert_rate)
        )
        expected_score = round(weighted / (0.30 + 0.25 + 0.20 + 0.15), 6)

        assert result["proposed" if "proposed" in result else "scope"] is not None
        assert result["score"] == expected_score
        assert result["status"] == "partial"  # incidentLinkage stays unknown
        assert result["components"]["firstPassYield"]["value"] == fpy
        assert result["components"]["rejectionRate"]["value"] == rate
        assert result["components"]["calibrationError"]["value"] == calibration
        assert (
            result["components"]["postMergeRevertRate"]["value"] == revert_rate
        )
        envelope = result["coverageEnvelope"]
        _assert_complete_envelope(
            envelope,
            value=result["score"],
            available=13334,  # agent-one's diffs: ceil(40_000 / 3)
            sequence_range=(1, N_DIFFS),
        )


class TestReasonDistributionAt50k:
    def test_equals_full_scan_recomputation(self, big):
        result = _timed(
            "trust/reasonDistribution",
            lambda: compute_reason_distribution(big),
        )
        counts: dict[str, int] = {}
        for (reason,) in _raw(
            big,
            "SELECT COALESCE(rework_reason, 'other') FROM ledger_entry"
            " WHERE action_type='rejection'",
        ):
            counts[reason] = counts.get(reason, 0) + 1
        assert result["total"] == N_REJECTIONS
        assert result["total"] == sum(counts.values())
        assert result["byClass"] == {
            reason: {"count": count, "rate": round(count / N_REJECTIONS, 6)}
            for reason, count in sorted(counts.items())
        }
        _assert_complete_envelope(
            result["coverage"],
            value=N_REJECTIONS,
            available=N_REJECTIONS,
            sequence_range=(N_DIFFS + 1, N_DIFFS + N_REJECTIONS),
        )


class TestJcurveAt50k:
    def test_equals_full_scan_recomputation(self, big):
        result = _timed(
            "trust/jcurve",
            lambda: compute_jcurve(big, adoption_date=ADOPTION),
        )
        adoption_monday = _week_monday(_parse_ts(ADOPTION).date())
        weekly: dict[int, int] = {}
        rejected_before = rejected_after = 0
        proposed_before = proposed_after = 0
        linked = _linked_sequences(big)
        for (ts, decision, seq) in _raw(
            big,
            "SELECT ts_utc, decision, seq FROM ledger_entry"
            " WHERE action_type='diff'",
        ):
            rel = (
                _week_monday(_parse_ts(ts).date()) - adoption_monday
            ).days // 7
            weekly[rel] = weekly.get(rel, 0) + 1
            rejected = seq in linked or decision in ("rejected", "reworked")
            if rel < 0:
                proposed_before += 1
                rejected_before += rejected
            else:
                proposed_after += 1
                rejected_after += rejected

        before_weeks = list(range(min(w for w in weekly if w < 0), 0))
        after_weeks = list(range(0, max(w for w in weekly if w >= 0) + 1))
        baseline = round(
            sum(weekly.get(w, 0) for w in before_weeks) / len(before_weeks), 6
        )
        assert result["status"] == "ok"
        assert result["baseline"] == baseline
        assert result["phases"]["before"]["proposed"] == proposed_before
        assert result["phases"]["before"]["rejected"] == rejected_before
        assert result["phases"]["before"]["stabilityRate"] == round(
            rejected_before / proposed_before, 6
        )
        assert result["phases"]["after"]["proposed"] == proposed_after
        assert result["phases"]["after"]["rejected"] == rejected_after
        # Weekly bucketing agrees cell for cell.
        assert result["phases"]["before"]["weeklyThroughput"] == {
            str(w): weekly.get(w, 0) for w in before_weeks
        }
        _assert_complete_envelope(
            result["coverage"],
            value=result["baseline"],
            available=N_DIFFS,
            sequence_range=(1, N_DIFFS),
        )


class TestDoraAt50k:
    def test_equals_full_scan_recomputation(self, big):
        result = _timed(
            "trust/doraExport",
            lambda: compute_dora_metrics(big),
        )
        rows = [
            (seq, story, ts, decision)
            for (seq, story, ts, decision) in _raw(
                big,
                "SELECT seq, story_id, ts_utc, decision FROM ledger_entry"
                " WHERE action_type='diff'",
            )
        ]
        linked = _linked_sequences(big)
        approved = [r for r in rows if r[3] == "approved"]
        failures = [r for r in approved if r[0] in linked]

        # deployment_frequency: approved per week over the observed span.
        mondays = [_week_monday(_parse_ts(r[2]).date()) for r in approved]
        first = min(mondays)
        per_week: dict[int, int] = {}
        for monday in mondays:
            rel = (monday - first).days // 7
            per_week[rel] = per_week.get(rel, 0) + 1
        span_weeks = max(per_week) + 1
        assert result["metrics"]["deploymentFrequency"] == {
            "status": "ok",
            "value": round(len(approved) / span_weeks, 6),
            "deployments": len(approved),
            "spanWeeks": span_weeks,
            "note": result["metrics"]["deploymentFrequency"]["note"],
        }

        # change_failure_rate.
        assert result["metrics"]["changeFailureRate"]["value"] == round(
            len(failures) / len(approved), 6
        )
        assert result["metrics"]["changeFailureRate"]["failed"] == len(failures)

        # lead_time_for_changes: median story first-diff -> first-approved.
        lead_times = []
        for story in {r[1] for r in approved}:
            story_rows = [r for r in rows if r[1] == story]
            story_approved = [r for r in story_rows if r[3] == "approved"]
            first_proposed = min(_parse_ts(r[2]) for r in story_rows)
            first_approved = min(_parse_ts(r[2]) for r in story_approved)
            if first_approved > first_proposed:
                lead_times.append(
                    (first_approved - first_proposed).total_seconds() / 3600
                )
        assert result["metrics"]["leadTimeForChanges"]["value"] == round(
            statistics.median(lead_times), 6
        )
        assert result["metrics"]["leadTimeForChanges"]["stories"] == len(
            lead_times
        )

        # time_to_restore: failure -> next approved on the story.
        earliest_rejection = {
            row[0]: _parse_ts(row[1])
            for row in _raw(
                big,
                "SELECT rejected_sequence, MIN(ts_utc) FROM ledger_entry"
                " WHERE action_type='rejection' AND rejected_sequence IS NOT NULL"
                " GROUP BY rejected_sequence",
            )
        }
        restore_times = []
        for row in failures:
            failed_at = earliest_rejection[row[0]]
            recovery = [
                _parse_ts(other[2])
                for other in approved
                if other[1] == row[1] and _parse_ts(other[2]) > failed_at
            ]
            if recovery:
                restore_times.append(
                    (min(recovery) - failed_at).total_seconds() / 3600
                )
        assert result["metrics"]["timeToRestore"]["value"] == round(
            statistics.median(restore_times), 6
        )
        assert result["metrics"]["timeToRestore"]["failures"] == len(
            restore_times
        )
        _assert_complete_envelope(
            result["coverage"], available=N_DIFFS, sequence_range=(1, N_DIFFS)
        )


class TestCompareAgentsAt50k:
    def test_equals_full_scan_recomputation(self, big):
        story = "STORY-00"
        actors = ["agent-one", "agent-two"]
        result = _timed(
            "trust/compareAgents",
            lambda: compute_agent_comparison(
                big, story_id=story, actor_ids=actors
            ),
        )
        rows = [
            (seq, actor, action_type, ts, decision, tokens_in, tokens_out, cost)
            for (seq, actor, action_type, ts, decision, tokens_in, tokens_out, cost)
            in _raw(
                big,
                "SELECT seq, actor_id, action_type, ts_utc, decision,"
                " tokens_in, tokens_out, cost_usd FROM ledger_entry"
                " WHERE story_id=?",
                (story,),
            )
        ]
        linked = _linked_sequences(big)
        story_tokens = sum(
            (tin or 0) + (tout or 0) for *_, tin, tout, _cost in rows
        )
        for actor in actors:
            agent = result["agents"][actor]
            diffs = [r for r in rows if r[1] == actor and r[2] == "diff"]
            proposed = len(diffs)
            rejected = sum(
                1
                for r in diffs
                if r[0] in linked or r[4] in ("rejected", "reworked")
            )
            assert agent["yield"]["status"] == "ok"
            assert agent["yield"]["proposed"] == proposed
            assert agent["yield"]["rejected"] == rejected
            assert agent["yield"]["value"] == round(1 - rejected / proposed, 6)

            actor_rows = [r for r in rows if r[1] == actor]
            total_usd = sum(r[7] or 0.0 for r in actor_rows)
            tokens_in = sum(r[5] or 0 for r in actor_rows)
            tokens_out = sum(r[6] or 0 for r in actor_rows)
            assert agent["cost"]["totalUsd"] == round(total_usd, 6)
            assert agent["cost"]["tokensIn"] == tokens_in
            assert agent["cost"]["tokensOut"] == tokens_out
            assert agent["llmRatio"]["value"] == round(
                (tokens_in + tokens_out) / story_tokens, 6
            )
        assert result["coverage"]["truncated"] is False
        assert result["coverage"]["rowsAvailable"] == len(rows)
        assert result["coverage"]["rowsConsidered"] == len(rows)
        assert result["coverage"]["coverage"] == 1.0
        assert result["coverage"]["sequenceRange"] == [
            min(r[0] for r in rows),
            max(r[0] for r in rows),
        ]


class TestSpendAt50k:
    """The spend side over the same 50k: the dimension bill, the monthly
    totals and the forecast, each against a raw-SQL oracle."""

    def test_spend_totals_equal_full_scan(self, big):
        rows, available = scan_scope(big)
        assert available == N_ENTRIES
        result = _timed(
            "spend/series (dimension totals)",
            lambda: spend_by_dimension(rows, "vendor"),
        )
        oracle_tokens_in = oracle_tokens_out = 0
        oracle_cost = 0.0
        oracle_entries = 0
        for (tin, tout, cost) in _raw(
            big,
            "SELECT tokens_in, tokens_out, cost_usd FROM ledger_entry",
        ):
            if not (tin or tout or cost):
                continue
            oracle_entries += 1
            oracle_tokens_in += tin or 0
            oracle_tokens_out += tout or 0
            oracle_cost += float(cost or 0.0)
        totals = result["totals"]
        assert totals["entries"] == oracle_entries
        assert totals["tokensIn"] == oracle_tokens_in
        assert totals["tokensOut"] == oracle_tokens_out
        assert totals["recordedCostUsd"] == round(oracle_cost, 6)

    def test_monthly_totals_equal_full_scan(self, big):
        rows, _available = scan_scope(big)
        result = _timed(
            "spend/forecast (monthly totals)",
            lambda: monthly_spend_totals(rows),
        )
        oracle: dict[str, float] = {}
        for (ts, tin, tout, cost) in _raw(
            big,
            "SELECT ts_utc, tokens_in, tokens_out, cost_usd FROM ledger_entry",
        ):
            if not (tin or tout or cost) or not ts:
                continue
            month = ts[:7]
            oracle[month] = round(
                oracle.get(month, 0.0) + float(cost or 0.0), 6
            )
        assert result == dict(sorted(oracle.items()))

    def test_forecast_equals_independent_least_squares(self, big):
        rows, available = scan_scope(big)
        months = monthly_spend_totals(rows)
        current_month = "2026-06"  # deterministic window, like the sidecar's
        result = _timed(
            "spend/forecast (least squares)",
            lambda: forecast_monthly_spend(months, current_month),
        )
        assert result["status"] == "ok"
        # Independent OLS over the trailing 3 months (zero months in).
        trailing = [
            float(months.get(label, 0.0))
            for label in ("2026-03", "2026-04", "2026-05")
        ]
        n = float(len(trailing))
        sum_x = sum(range(len(trailing)))
        sum_y = sum(trailing)
        sum_xx = sum(x * x for x in range(len(trailing)))
        sum_xy = sum(x * y for x, y in enumerate(trailing))
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n
        projected = intercept + slope * len(trailing)
        assert result["slopeUsdPerMonth"] == round(slope, 6)
        assert result["projectedUsd"] == round(max(projected, 0.0), 6)
        assert available == N_ENTRIES


class TestEnvelopeRidesTheRpcResults:
    """AC-41: the envelope is on the wire, in the same result — never a
    second call (NFR-34)."""

    def _call(self, server, method, params):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 41, "method": method, "params": params}
        )
        assert response is not None and "error" not in response, response
        return response["result"]

    def test_trust_and_spend_rpcs_carry_the_envelope(self, big):
        server = SidecarServer(ledger=big)
        rate = self._call(server, "trust/rejectionRate", {})
        _assert_complete_envelope(rate["coverage"], value=rate["rate"])
        assert rate["cacheHit"] is False
        cached = self._call(server, "trust/rejectionRate", {})
        assert cached["cacheHit"] is True

        series = self._call(server, "spend/series", {"dimension": "vendor"})
        _assert_complete_envelope(
            series["coverage"], value=series["totals"]["costUsd"]
        )

        forecast = self._call(server, "spend/forecast", {})
        envelope = forecast["coverage"]
        assert envelope["truncated"] is False
        assert envelope["rowsAvailable"] == N_ENTRIES
        assert envelope["rowsConsidered"] == N_ENTRIES
        assert forecast["forecast"]["status"] in (
            "ok",
            "insufficient_evidence",
        )
        assert forecast["status"] != "truncated"
