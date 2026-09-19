"""Spend ceilings (FR-M39-02) and monthly forecast + budget alert
(FR-M39-03; F1 Workstream F tasks 27-28).

Ceilings come from config (the governance pack's budgetCeilings), never
hard-coded. The hosted/observed enforcement split is the server handler's
job (test_spend_rpc.py); here the deterministic rules.
"""

from __future__ import annotations

from meridian_core.metrics import (
    check_spend_ceiling,
    forecast_monthly_spend,
    monthly_spend_totals,
)

#: 2026-01 rows (calendar month 2026-01), 2025-12 rows (month 2025-12).
ROWS = [
    {"seq": 1, "actor_id": "a", "story_id": "S", "vendor": "acp",
     "ts_utc": "2025-12-01T10:00:00Z", "tokens_in": 1000, "tokens_out": 0,
     "cost_usd": 1.0},
    {"seq": 2, "actor_id": "a", "story_id": "S", "vendor": "acp",
     "ts_utc": "2025-12-15T10:00:00Z", "tokens_in": 1000, "tokens_out": 0,
     "cost_usd": 2.0},
    {"seq": 3, "actor_id": "a", "story_id": "S", "vendor": "acp",
     "ts_utc": "2026-01-05T10:00:00Z", "tokens_in": 1000, "tokens_out": 0,
     "cost_usd": 3.0},
    {"seq": 4, "actor_id": "b", "story_id": "S", "vendor": "anthropic",
     "ts_utc": "2026-01-20T10:00:00Z", "tokens_in": 2000, "tokens_out": 0,
     "cost_usd": None},  # priced: 2M tokens x 2/M = 4.0
    {"seq": 5, "actor_id": "a", "story_id": "S", "vendor": "acp",
     "ts_utc": "2026-01-21T10:00:00Z", "tokens_in": 0, "tokens_out": 0,
     "cost_usd": None},  # no tokens, no cost -> not a spend record
]

PRICE = lambda vendor, model, tin, tout: (tin + tout) * 2e-6


class TestMonthlyTotals:
    def test_totals_bucket_by_calendar_month(self):
        totals = monthly_spend_totals(ROWS)
        assert totals == {"2025-12": 3.0, "2026-01": 3.0}  # unpriced: b's
        # 2M tokens have no cost and no pricer -> not spend evidence.

    def test_pricer_estimates_missing_cost(self):
        totals = monthly_spend_totals(ROWS, PRICE)
        # b's 2,000 tokens price at 0.002M x 2/M = 0.004 alongside the
        # 3.0 recorded for January.
        assert totals == {"2025-12": 3.0, "2026-01": 3.004}

    def test_empty_rows_give_empty_totals(self):
        assert monthly_spend_totals([], PRICE) == {}


class TestCeilingCheck:
    def test_below_ceiling_not_breached(self):
        result = check_spend_ceiling(10.0, 25)
        assert result["configured"] is True
        assert result["breached"] is False
        assert result["headroomUsd"] == 15.0

    def test_at_ceiling_is_breached(self):
        # The ceiling PAUSES — reaching it is enough, no overspend needed.
        result = check_spend_ceiling(25.0, 25)
        assert result["breached"] is True
        assert result["headroomUsd"] == 0.0

    def test_no_ceiling_configured_is_not_breach(self):
        result = check_spend_ceiling(1e9, None)
        assert result["configured"] is False
        assert result["breached"] is False

    def test_malformed_ceiling_config_is_not_breach(self):
        for bad in ("lots", -1, True):
            result = check_spend_ceiling(1e9, bad)
            assert result["configured"] is False
            assert result["breached"] is False


class TestForecast:
    def test_linear_projection_of_rising_spend(self):
        # Trailing 3 months of 2026-03: 10, 20, 30 -> line y = 10 + 10x at
        # x=3 (2026-03 itself) projects 40.
        totals = {"2025-12": 10.0, "2026-01": 20.0, "2026-02": 30.0}
        forecast = forecast_monthly_spend(totals, "2026-03")
        assert forecast["status"] == "ok"
        assert forecast["projectedUsd"] == 40.0
        assert forecast["slopeUsdPerMonth"] == 10.0
        assert "least-squares" in forecast["method"]

    def test_zero_months_count_as_evidence(self):
        # 100, 0, 100: two evidence months — a projection is possible and
        # the zero month is real evidence of no spend, not a missing month.
        totals = {"2025-12": 100.0, "2026-02": 100.0}
        forecast = forecast_monthly_spend(totals, "2026-03")
        assert forecast["status"] == "ok"
        assert forecast["evidenceMonths"] == 2
        # y = [100, 0, 100]: slope 0, intercept 200/3 -> projected 200/3.
        assert forecast["projectedUsd"] == round(200 / 3, 6)

    def test_single_month_is_insufficient_evidence(self):
        forecast = forecast_monthly_spend({"2026-02": 5.0}, "2026-03")
        assert forecast["status"] == "insufficient_evidence"
        assert forecast["projectedUsd"] is None

    def test_no_months_is_insufficient_evidence(self):
        forecast = forecast_monthly_spend({}, "2026-03")
        assert forecast["status"] == "insufficient_evidence"

    def test_negative_trend_floors_at_zero(self):
        totals = {"2025-12": 10.0, "2026-01": 5.0, "2026-02": 1.0}
        forecast = forecast_monthly_spend(totals, "2026-03")
        assert forecast["status"] == "ok"
        assert forecast["projectedUsd"] == 0.0
        assert forecast["slopeUsdPerMonth"] < 0

    def test_deterministic_same_input_same_output(self):
        totals = {"2025-12": 3.0, "2026-01": 7.0, "2026-02": 9.0}
        first = forecast_monthly_spend(totals, "2026-03")
        second = forecast_monthly_spend(dict(totals), "2026-03")
        assert first == second
