"""Cross-vendor spend feed (FR-M39-01; F1 Workstream F task 26).

The feed adapts recorded ledger rows onto the SpendSeries protocol
(D26) and aggregates the six FR-M39-01 dimensions. Dimensions with no
recorded evidence report 'unknown' — never fabricated.
"""

from __future__ import annotations

import pytest

from meridian_core.metrics import (
    DIMENSIONS,
    UNKNOWN,
    LedgerSpendSeries,
    StoryMetadata,
    parse_story_metadata,
    period_label,
    spend_by_dimension,
    spend_records,
)

#: 2026-01-05 is in ISO week 2026-W02, calendar month 2026-01.
ROW_ACME_W02 = {
    "seq": 1,
    "actor_id": "agent-one",
    "story_id": "S-1",
    "vendor": "anthropic",
    "model_id": "claude-sonnet-4-5",
    "external_session_id": "sess-observed",
    "ts_utc": "2026-01-05T10:00:00Z",
    "tokens_in": 1000,
    "tokens_out": 500,
    "cost_usd": 0.01,
}
ROW_ACME_W03_NO_MODEL = {
    "seq": 2,
    "actor_id": "agent-one",
    "story_id": "S-2",
    "vendor": "anthropic",
    "model_id": None,
    "ts_utc": "2026-01-12T10:00:00Z",
    "tokens_in": 2000,
    "tokens_out": 1000,
    "cost_usd": 0.02,
}
ROW_ACP_W03 = {
    "seq": 3,
    "actor_id": "agent-two",
    "story_id": "S-1",
    "vendor": "acp",
    "model_id": "claude-haiku-4-5",
    "external_session_id": "sess-hosted",
    "ts_utc": "2026-01-12T11:00:00Z",
    "tokens_in": 500,
    "tokens_out": 250,
    "cost_usd": 0.005,
}
ROW_NATIVE_W02 = {
    "seq": 4,
    "actor_id": "meridian-loop",
    "story_id": "S-2",
    "vendor": "meridian",
    "model_id": None,
    "ts_utc": "2026-01-06T09:00:00Z",
    "tokens_in": 10,
    "tokens_out": 5,
    "cost_usd": None,
}
ROW_NO_TOKENS = {
    "seq": 5,
    "actor_id": "agent-one",
    "story_id": "S-1",
    "vendor": "anthropic",
    "model_id": "claude-sonnet-4-5",
    "ts_utc": "2026-01-07T10:00:00Z",
    "tokens_in": None,
    "tokens_out": None,
    "cost_usd": None,
    "action_type": "diff",
}

ROWS = [ROW_ACME_W02, ROW_ACME_W03_NO_MODEL, ROW_ACP_W03, ROW_NATIVE_W02, ROW_NO_TOKENS]

META = StoryMetadata(
    source="test",
    entries={
        "*": {"team": "platform", "costCentre": "CC-100"},
        "S-2": {"team": "payments", "costCentre": "CC-210"},
    },
)


class TestPeriodLabels:
    def test_iso_week_label(self):
        assert period_label("2026-01-05T10:00:00Z") == "2026-W02"

    def test_month_label(self):
        assert period_label("2026-01-05T10:00:00Z", "month") == "2026-01"

    def test_unparseable_is_none(self):
        assert period_label("not-a-date") is None
        assert period_label(None) is None


class TestSpendRecords:
    def test_only_token_bearing_rows_are_records(self):
        records = spend_records(ROWS)
        assert [r["seq"] for r in records] == [1, 2, 3, 4]

    def test_recorded_cost_is_reported(self):
        records = spend_records(ROWS)
        assert records[0]["recordedCostUsd"] == 0.01
        assert records[0]["estimatedCostUsd"] is None

    def test_tokens_without_cost_can_be_priced(self):
        price = lambda vendor, model, tin, tout: round((tin + tout) * 1e-6, 6)
        records = spend_records([ROW_NATIVE_W02], price)
        assert records[0]["estimatedCostUsd"] == 15e-6

    def test_no_pricer_leaves_estimate_none(self):
        records = spend_records([ROW_NATIVE_W02])
        assert records[0]["estimatedCostUsd"] is None


class TestLedgerSpendSeries:
    """The D26 adapter: ledger rows onto the SpendSeries protocol."""

    def test_points_sum_tokens_per_iso_week(self):
        series = LedgerSpendSeries(ROWS)
        points = series.points("agent-one")
        assert [(p.period, p.tokens) for p in points] == [
            ("2026-W02", 1500),
            ("2026-W03", 3000),
        ]

    def test_agents_lists_token_bearing_actors(self):
        series = LedgerSpendSeries(ROWS)
        assert list(series.agents()) == ["agent-one", "agent-two", "meridian-loop"]

    def test_unknown_agent_has_no_points(self):
        series = LedgerSpendSeries(ROWS)
        assert series.points("ghost") == []

    def test_consumable_by_tokenmaxxing_detector(self):
        from meridian_core.metrics import detect_tokenmaxxing, YieldPoint

        weeks = ["2026-W01", "2026-W02", "2026-W03", "2026-W04"]
        rows = [
            {
                "seq": i + 1,
                "actor_id": "agent-one",
                "story_id": "S",
                "vendor": "anthropic",
                "model_id": "m",
                "ts_utc": ts,
                "tokens_in": tokens,
                "tokens_out": 0,
                "cost_usd": 0.0,
            }
            for i, (ts, tokens) in enumerate(
                [
                    ("2025-12-29T10:00:00Z", 100),  # W01
                    ("2026-01-05T10:00:00Z", 100),  # W02
                    ("2026-01-12T10:00:00Z", 100),  # W03
                    ("2026-01-19T10:00:00Z", 200),  # W04
                ]
            )
        ]
        series = LedgerSpendSeries(rows)
        verdict = detect_tokenmaxxing(
            series.points("agent-one"),
            [YieldPoint(period, 0.5) for period in weeks],
            min_periods=4,
        )
        # The feed's periods/tokens drive the detector's own rule:
        # 200 -> 300 across the half split is a 1.5x rise on flat yield.
        assert verdict["status"] == "ok"
        assert verdict["spendTrend"] == 1.5
        assert verdict["flagged"] is True


class TestSpendByDimension:
    """All six FR-M39-01 dimensions over the fixture rows."""

    def test_six_dimensions_enumerated(self):
        assert DIMENSIONS == ("vendor", "model", "agent", "story", "team", "costCentre")

    def test_by_vendor(self):
        result = spend_by_dimension(ROWS, "vendor")
        values = result["byValue"]
        assert values["anthropic"]["tokens"] == 4500
        assert values["acp"]["tokens"] == 750
        assert values["meridian"]["tokens"] == 15

    def test_by_model_unknown_when_not_recorded(self):
        result = spend_by_dimension(ROWS, "model")
        values = result["byValue"]
        assert values["claude-sonnet-4-5"]["tokens"] == 1500
        assert values["claude-haiku-4-5"]["tokens"] == 750
        assert UNKNOWN in values  # the row with model_id null
        assert values[UNKNOWN]["tokens"] == 3015

    def test_by_agent(self):
        result = spend_by_dimension(ROWS, "agent")
        assert result["byValue"]["agent-one"]["tokens"] == 4500
        assert result["byValue"]["agent-two"]["tokens"] == 750

    def test_by_story(self):
        result = spend_by_dimension(ROWS, "story")
        assert result["byValue"]["S-1"]["tokens"] == 2250
        assert result["byValue"]["S-2"]["tokens"] == 3015

    def test_by_team_resolves_through_story_metadata(self):
        result = spend_by_dimension(ROWS, "team", story_meta=META)
        values = result["byValue"]
        # S-1 -> wildcard platform; S-2 -> explicit payments.
        assert values["platform"]["tokens"] == 2250
        assert values["payments"]["tokens"] == 3015

    def test_by_cost_centre_resolves_through_story_metadata(self):
        result = spend_by_dimension(ROWS, "costCentre", story_meta=META)
        assert result["byValue"]["CC-100"]["tokens"] == 2250
        assert result["byValue"]["CC-210"]["tokens"] == 3015

    def test_no_metadata_is_unknown_never_fabricated(self):
        result = spend_by_dimension(ROWS, "team")
        assert list(result["byValue"].keys()) == [UNKNOWN]
        assert result["byValue"][UNKNOWN]["tokens"] == 5265

    def test_totals_carry_recorded_cost(self):
        result = spend_by_dimension(ROWS, "vendor")
        assert result["totals"]["recordedCostUsd"] == 0.035
        assert result["totals"]["tokens"] == 5265

    def test_bad_dimension_refused(self):
        with pytest.raises(ValueError):
            spend_by_dimension(ROWS, "colour")


class TestStoryMetadataPack:
    def test_parse_valid_pack(self):
        meta = parse_story_metadata(
            "version: 1\nstories:\n  S-1:\n    team: platform\n    costCentre: CC-100\n",
            "test",
        )
        assert not meta.fail_closed
        assert meta.lookup("S-1") == {"team": "platform", "costCentre": "CC-100"}
        assert meta.lookup("S-other") == {"team": UNKNOWN, "costCentre": UNKNOWN}

    def test_wildcard_default_applies(self):
        meta = parse_story_metadata(
            'version: 1\nstories:\n  "*":\n    team: platform\n',
            "test",
        )
        assert meta.lookup("S-other") == {"team": "platform", "costCentre": UNKNOWN}

    def test_empty_values_are_unknown(self):
        meta = parse_story_metadata(
            'version: 1\nstories:\n  S-1:\n    team: ""\n    costCentre: CC-1\n',
            "test",
        )
        assert meta.fail_closed  # an empty team is a schema violation
        assert meta.lookup("S-1") == {"team": UNKNOWN, "costCentre": UNKNOWN}

    def test_malformed_pack_fails_closed(self):
        meta = parse_story_metadata("version: nope\n", "test")
        assert meta.fail_closed
        assert meta.lookup("S-1") == {"team": UNKNOWN, "costCentre": UNKNOWN}

    def test_not_yaml_fails_closed(self):
        meta = parse_story_metadata("{unclosed", "test")
        assert meta.fail_closed

    def test_load_first_readable_wins(self, tmp_path):
        override = tmp_path / "stories.yaml"
        override.write_text(
            "version: 1\nstories:\n  S-9:\n    team: edge\n", encoding="utf-8"
        )
        meta = StoryMetadata()  # default: everything unknown
        loaded = __import__(
            "meridian_core.metrics", fromlist=["load_story_metadata"]
        ).load_story_metadata([override, tmp_path / "missing.yaml"])
        assert loaded.lookup("S-9")["team"] == "edge"
        assert meta.lookup("S-9")["team"] == UNKNOWN
