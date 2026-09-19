"""Tokenmaxxing detection (FR-M37-07; F1 Workstream E task 24).

FR-M37-07: warn on **tokenmaxxing** — rising token spend without rising
first-pass yield — per agent and per team. The detector is built against a
spend-series interface, not a concrete feed: the M39 cross-vendor spend
pipeline lands in a later task and will adapt its records onto
:class:`SpendPoint` / :class:`YieldPoint`; the tests here drive the
detector with fixture series, and ``trust/tokenmaxxing`` derives the yield
half from the ledger.

The rule (documented here as the brief requires):

* the series is split in half — the **recent window** (the newest half of
  periods) against the **previous window** (the older half);
* **spend rise** — ``sum(recent tokens) / sum(previous tokens)``; spend
  counts as *rising* at or above ``spend_rise_threshold`` (default 1.25,
  i.e. a ≥25% rise);
* **yield** — first-pass yield (0..1) per period, supplied by the caller;
  periods without yield evidence are excluded from the yield halves, and
  *rising* means ``mean(recent yield) > mean(previous yield)``;
* **flagged** — spend rising AND yield not rising. Flat yield with rising
  spend is the pattern FR-M37-07 names: more tokens, no more yield;
* **insufficient evidence** — fewer than ``min_periods`` periods (default
  4), a window with no spend, or no yield evidence on either side: the
  verdict reports the evidence it has and never flags on fabricated
  numbers. An agent whose yield the ledger cannot evidence at all reports
  ``unknown``.

Zero model calls (FR-M36-07): arithmetic over two small series.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

__all__ = [
    "DEFAULT_MIN_PERIODS",
    "DEFAULT_SPEND_RISE_THRESHOLD",
    "SpendPoint",
    "SpendSeries",
    "YieldPoint",
    "detect_tokenmaxxing",
]

DEFAULT_SPEND_RISE_THRESHOLD = 1.25
DEFAULT_MIN_PERIODS = 4


@dataclass(frozen=True)
class SpendPoint:
    """Token spend for one period of one agent (or of the whole team)."""

    period: str  #: an ISO-week label ("2026-W01") or any ordered token
    tokens: float


@dataclass(frozen=True)
class YieldPoint:
    """First-pass yield (0..1) for one period, derived from the ledger."""

    period: str
    first_pass_yield: float


@runtime_checkable
class SpendSeries(Protocol):
    """The interface the M39 spend feed will implement (task 26 adapts the
    real records; the detector only reads this)."""

    def points(self, agent_id: str) -> Sequence[SpendPoint]: ...

    def agents(self) -> Sequence[str]: ...


def detect_tokenmaxxing(
    spend: Sequence[SpendPoint],
    yields: Sequence[YieldPoint],
    *,
    spend_rise_threshold: float = DEFAULT_SPEND_RISE_THRESHOLD,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> dict[str, Any]:
    """The FR-M37-07 verdict for one series (an agent, or the team total).

    Returns ``{status, flagged, periods, spendTrend, yieldTrend, note}`` —
    ``status`` is ``ok`` (both halves judged), ``insufficient_evidence``
    (too few periods or a window without spend/yield) or ``unknown``;
    ``flagged`` is never true unless status is ``ok``.
    """
    ordered = sorted(spend, key=lambda point: point.period)
    if len(ordered) < min_periods:
        return {
            "status": "insufficient_evidence",
            "flagged": False,
            "periods": len(ordered),
            "spendTrend": None,
            "yieldTrend": None,
            "note": f"fewer than {min_periods} periods of spend evidence",
        }

    half = len(ordered) // 2
    previous_spend = ordered[:half]
    recent_spend = ordered[half:]
    previous_total = sum(point.tokens for point in previous_spend)
    recent_total = sum(point.tokens for point in recent_spend)
    if previous_total <= 0:
        return {
            "status": "insufficient_evidence",
            "flagged": False,
            "periods": len(ordered),
            "spendTrend": None,
            "yieldTrend": None,
            "note": "no recorded spend in the previous window",
        }
    spend_trend = round(recent_total / previous_total, 6)

    yield_by_period = {point.period: point.first_pass_yield for point in yields}
    previous_yield = [
        yield_by_period[point.period]
        for point in previous_spend
        if point.period in yield_by_period
    ]
    recent_yield = [
        yield_by_period[point.period]
        for point in recent_spend
        if point.period in yield_by_period
    ]
    if not previous_yield or not recent_yield:
        return {
            "status": "unknown",
            "flagged": False,
            "periods": len(ordered),
            "spendTrend": spend_trend,
            "yieldTrend": None,
            "note": "the ledger evidences no first-pass yield for one of the windows",
        }

    previous_mean = sum(previous_yield) / len(previous_yield)
    recent_mean = sum(recent_yield) / len(recent_yield)
    yield_trend = round(recent_mean - previous_mean, 6)
    spend_rising = spend_trend >= spend_rise_threshold
    yield_rising = yield_trend > 0

    return {
        "status": "ok",
        "flagged": bool(spend_rising and not yield_rising),
        "periods": len(ordered),
        "spendTrend": spend_trend,
        "yieldTrend": yield_trend,
        "previousYield": round(previous_mean, 6),
        "recentYield": round(recent_mean, 6),
        "note": (
            "spend rising without rising first-pass yield"
            if spend_rising and not yield_rising
            else (
                "spend rising with rising first-pass yield"
                if spend_rising
                else "spend not rising"
            )
        ),
    }
