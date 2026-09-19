"""Tokenmaxxing detection (FR-M37-07; F1 Workstream E task 24).

Rising token spend without rising first-pass yield, per agent and per
team. The detector is built against a spend-series interface and driven
here with fixture series; trust/tokenmaxxing derives the yield half from
the ledger. Verdicts without evidence are labelled, never fabricated.
"""

from __future__ import annotations

import pytest

import bus_types

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import SpendPoint, YieldPoint, detect_tokenmaxxing
from meridian_core.server import SidecarServer

PERIODS = ["2026-W01", "2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06"]


def _spend(tokens_by_period):
    return [
        SpendPoint(period, tokens)
        for period, tokens in zip(PERIODS, tokens_by_period)
    ]


def _yield(points):
    return [YieldPoint(period, value) for period, value in points]


class TestDetector:
    """The FR-M37-07 rule over fixture series: recent half vs previous
    half, spend rising while yield is not."""

    def test_flagged_when_spend_rises_and_yield_does_not(self):
        result = detect_tokenmaxxing(
            _spend([100, 100, 100, 100, 200, 220]),
            _yield(
                [
                    ("2026-W01", 0.5), ("2026-W02", 0.5),
                    ("2026-W03", 0.5), ("2026-W04", 0.5),
                    ("2026-W05", 0.5), ("2026-W06", 0.5),
                ]
            ),
        )
        assert result["status"] == "ok"
        assert result["flagged"] is True
        assert result["spendTrend"] == round(520 / 300, 6)
        assert result["yieldTrend"] == 0.0

    def test_not_flagged_when_yield_rises_too(self):
        result = detect_tokenmaxxing(
            _spend([100, 100, 100, 100, 200, 220]),
            _yield(
                [
                    ("2026-W01", 0.4), ("2026-W02", 0.4),
                    ("2026-W03", 0.4), ("2026-W04", 0.4),
                    ("2026-W05", 0.7), ("2026-W06", 0.8),
                ]
            ),
        )
        assert result["flagged"] is False
        assert result["yieldTrend"] > 0

    def test_not_flagged_when_spend_flat(self):
        result = detect_tokenmaxxing(
            _spend([100, 110, 100, 100, 100, 110]),
            _yield([(p, 0.5) for p in PERIODS]),
        )
        assert result["flagged"] is False
        assert result["note"] == "spend not rising"

    def test_threshold_boundary(self):
        # 200/200 = 1.0: below the 1.25 default -> not rising.
        result = detect_tokenmaxxing(
            _spend([100, 100, 100, 100, 100, 100]),
            _yield([(p, 0.5) for p in PERIODS]),
        )
        assert result["flagged"] is False

    def test_too_few_periods_is_insufficient_evidence(self):
        result = detect_tokenmaxxing(
            _spend([100, 200]),
            _yield([("2026-W01", 0.5), ("2026-W02", 0.5)]),
        )
        assert result["status"] == "insufficient_evidence"
        assert result["flagged"] is False
        assert result["spendTrend"] is None

    def test_no_yield_evidence_is_unknown_not_flagged(self):
        result = detect_tokenmaxxing(
            _spend([100, 100, 100, 100, 200, 220]), []
        )
        assert result["status"] == "unknown"
        assert result["flagged"] is False
        assert result["yieldTrend"] is None
        assert result["spendTrend"] is not None  # the spend fact is real

    def test_zero_previous_spend_is_insufficient_evidence(self):
        result = detect_tokenmaxxing(
            _spend([0, 0, 0, 100, 200, 220]),
            _yield([(p, 0.5) for p in PERIODS]),
        )
        assert result["status"] == "insufficient_evidence"
        assert result["flagged"] is False

    def test_periods_without_yield_are_excluded_not_fatal(self):
        result = detect_tokenmaxxing(
            _spend([100, 100, 100, 100, 200, 220]),
            _yield(
                [
                    ("2026-W01", 0.5), ("2026-W02", 0.5),
                    ("2026-W05", 0.5), ("2026-W06", 0.5),
                ]
            ),
        )
        assert result["status"] == "ok"
        assert result["flagged"] is True


def _entry(story, actor, ts, repo_id="edb", **extra):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": repo_id,
        "ts_utc": ts,
    }
    entry.update(extra)
    return entry


def _call(server, method, params):
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": 11, "method": method, "params": params}
    )
    assert response is not None
    assert "error" not in response, response.get("error")
    return response["result"]


# ISO weeks of the fixture timestamps (adoption-free, pure calendar):
# 2026-01-05 -> 2026-W02 ... one diff per listed week.
WEEK_TS = {
    "2026-W02": "2026-01-05T10:00:00Z",
    "2026-W03": "2026-01-12T10:00:00Z",
    "2026-W04": "2026-01-19T10:00:00Z",
    "2026-W05": "2026-01-26T10:00:00Z",
    "2026-W06": "2026-02-02T10:00:00Z",
    "2026-W07": "2026-02-09T10:00:00Z",
}

#: The spend series periods must name the SAME ISO weeks the ledger
#: buckets yields into — that matching is the interface.
SPEND_PERIODS = list(WEEK_TS)


class TestTokenmaxxingRpc:
    """trust/tokenmaxxing: fixture spend series + ledger-derived yield."""

    @pytest.fixture()
    def world(self, tmp_path):
        """agent-one flat yield (one rejection in the middle), agent-two
        rising yield (all clean recently)."""
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        server = SidecarServer(ledger=ledger)
        # agent-one: 2 diffs per week, one rejected in W06 (the recent
        # half) — yield does not rise across the series.
        for week in ("2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06", "2026-W07"):
            ledger.append(_entry("S", "agent-one", WEEK_TS[week]))
        seq = ledger.query(action_type="diff", limit=1000)[4]["seq"]  # agent-one W06
        ledger.append(
            {
                "story_id": "S",
                "phase": "review",
                "loop_id": "rejection",
                "loop_iteration": 0,
                "actor_id": "reviewer-human",
                "actor_version": "0",
                "actor_kind": "external",
                "policy_version": "f0",
                "action_type": "rejection",
                "decision": "rejected",
                "rework_reason": "other",
                "rejected_sequence": seq,
                "repo_id": "edb",
                "ts_utc": "2026-02-03T10:00:00Z",
            }
        )
        # agent-two: 2 diffs per week; W04's were rejected, clean
        # afterwards — yield rises across the series.
        for week in ("2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06", "2026-W07"):
            ledger.append(_entry("S", "agent-two", WEEK_TS[week]))
        seq2 = ledger.query(action_type="diff", limit=1000)[8]["seq"]  # agent-two W04
        ledger.append(
            {
                "story_id": "S",
                "phase": "review",
                "loop_id": "rejection",
                "loop_iteration": 0,
                "actor_id": "reviewer-human",
                "actor_version": "0",
                "actor_kind": "external",
                "policy_version": "f0",
                "action_type": "rejection",
                "decision": "rejected",
                "rework_reason": "other",
                "rejected_sequence": seq2,
                "repo_id": "edb",
                "ts_utc": "2026-01-20T11:00:00Z",
            }
        )
        yield server, ledger
        ledger.close()

    def _series(self, rising):
        base = [100, 100, 100, 100]
        tokens = base + ([200, 220] if rising else [100, 100])
        return [
            {"period": period, "tokens": value}
            for period, value in zip(SPEND_PERIODS, tokens)
        ]

    def test_agent_flagged_when_spend_rises_yield_flat(self, world):
        server, _ledger = world
        result = _call(
            server,
            "trust/tokenmaxxing",
            {"spendSeries": {"agent-one": self._series(rising=True)}},
        )
        one = result["byAgent"]["agent-one"]
        assert one["status"] == "ok"
        assert one["flagged"] is True
        # Yield halves: previous (W02,W03,W04) 1.0, recent (W05,W06,W07)
        # 2/3 (W06 was rejected) — not rising while spend went
        # 300 -> 520: tokenmaxxing.
        assert one["previousYield"] == 1.0
        assert one["recentYield"] == round(2 / 3, 6)
        assert one["spendTrend"] == round(520 / 300, 6)

    def test_agent_not_flagged_when_yield_rises(self, world):
        server, _ledger = world
        result = _call(
            server,
            "trust/tokenmaxxing",
            {"spendSeries": {"agent-two": self._series(rising=True)}},
        )
        two = result["byAgent"]["agent-two"]
        assert two["flagged"] is False
        # agent-two's rejection sits in the previous half: yield rises.
        assert two["recentYield"] > two["previousYield"]

    def test_team_verdict_aggregates_series(self, world):
        server, _ledger = world
        result = _call(
            server,
            "trust/tokenmaxxing",
            {
                "spendSeries": {
                    "agent-one": self._series(rising=True),
                    "agent-two": self._series(rising=True),
                }
            },
        )
        # Team tokens per period: [200,200,200,200,400,440]; pooled yield
        # per period: W02-W03 1.0, W04 0.5, W05 1.0, W06 0.5, W07 1.0 —
        # the pooled mean does not rise while spend goes 600 -> 840.
        team = result["team"]
        assert team["status"] == "ok"
        assert team["flagged"] is True
        assert team["spendTrend"] == round(1040 / 600, 6)
        assert team["yieldTrend"] == 0.0
        assert set(result["byAgent"].keys()) == {"agent-one", "agent-two"}

    def test_unknown_agent_yield_never_flagged(self, world):
        """A spend series for an actor the ledger has no diffs for reports
        unknown — the detector never flags on fabricated yield."""
        server, _ledger = world
        result = _call(
            server,
            "trust/tokenmaxxing",
            {"spendSeries": {"ghost": self._series(rising=True)}},
        )
        ghost = result["byAgent"]["ghost"]
        assert ghost["status"] == "unknown"
        assert ghost["flagged"] is False

    def test_missing_spend_series_refused(self, world):
        server, _ledger = world
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 11, "method": "trust/tokenmaxxing", "params": {}}
        )
        assert response["error"]["code"] == -32602  # INVALID_PARAMS

    def test_result_is_cached_then_invalidated_on_append(self, world):
        server, ledger = world
        params = {"spendSeries": {"agent-one": self._series(rising=True)}}
        _call(server, "trust/tokenmaxxing", params)
        cached = _call(server, "trust/tokenmaxxing", params)
        assert cached == _call(server, "trust/tokenmaxxing", params)

        # Reject the W07 agent-one diff: the fresh compute must see it.
        diff_rows = ledger.query(action_type="diff", limit=1000)
        w07 = [r for r in diff_rows if r["actor_id"] == "agent-one"][-1]
        ledger.append(
            {
                "story_id": "S",
                "phase": "review",
                "loop_id": "rejection",
                "loop_iteration": 0,
                "actor_id": "reviewer-human",
                "actor_version": "0",
                "actor_kind": "external",
                "policy_version": "f0",
                "action_type": "rejection",
                "decision": "rejected",
                "rework_reason": "other",
                "rejected_sequence": w07["seq"],
                "repo_id": "edb",
                "ts_utc": "2026-02-10T10:00:00Z",
            }
        )
        fresh = _call(server, "trust/tokenmaxxing", params)
        # Recent yield (W05,W06,W07) drops to (1 + 0 + 0)/3 — the cache
        # really was invalidated, not served stale.
        assert fresh["byAgent"]["agent-one"]["recentYield"] == round(1 / 3, 6)

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/tokenmaxxing" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"
