"""Spend ceilings, forecast and budget alerts (FR-M39-02/03; F1
Workstream F tasks 27-28).

FR-M39-02 — ceilings. A ceiling is a configured USD limit from the
governance pack's ``budgetCeilings`` section (FR-M12-08 — the section
governance.yaml already declares, "enforced by the spend surfaces").
The enforcement is honest about what Meridian controls:

* a **hosted** agent (a session Meridian launched over ACP — the
  session_begin record IS the hosted fact) breaches -> the check
  records the breach in the ledger (FR-M10-08: durable before any
  action) and dispatches a pause-at-checkpoint notification; the
  extension host owns the wire and pauses the session at its next
  checkpoint, exactly like gate.halt owns the record while the
  registry owns the kill;
* a Meridian-native actor (vendor 'meridian' — Meridian's own runtime
  loops) breaches -> the same pause-at-checkpoint dispatch; Meridian
  hosts its own loops too;
* an **observed** external agent (FR-M35-02/06) breaches -> an
  ADVISORY WARNING only, the same NOT_HOSTED honesty the steer surface
  uses: observation never intercepts, so the result says so in plain
  words — never a silent no-op, never a fake pause.

FR-M39-03 — forecast. Monthly spend per team is projected from the
trailing ledger with one deterministic method, documented here: the
trailing ``window_months`` calendar months (default 3, zero months
included — a month with no recorded token activity is real evidence of
no spend) get an ordinary least-squares line; the current month's
projection is that line evaluated at the current month. Two evidence
months minimum, else ``insufficient_evidence`` — no projection on one
point. The budget alert fires when the month-to-date actual OR the
projection crosses the configured ``budgetCeilings.usdPerMonth``:
``actual_breach`` / ``forecast_breach`` / ``ok``; no configured budget
reports ``unconfigured`` — the forecast is still returned.

Zero model calls (FR-M36-07): sums, one least-squares fit.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .spendfeed import PriceFn, spend_records

__all__ = [
    "DEFAULT_WINDOW_MONTHS",
    "check_spend_ceiling",
    "forecast_monthly_spend",
    "monthly_spend_totals",
]

DEFAULT_WINDOW_MONTHS = 3

#: Ceiling keys the surfaces understand (all optional, all from config).
CEILING_KEYS = ("usdPerAgent", "usdPerStory", "usdPerSession", "usdPerMonth")


def _spend_usd(
    rows: Sequence[Mapping[str, Any]], price: PriceFn | None = None
) -> tuple[float, int]:
    """(best-known USD, estimated-share USD) over token-bearing rows:
    recorded cost plus pack-priced estimates where cost was absent."""
    recorded = 0.0
    estimated = 0.0
    for record in spend_records(rows, price):
        recorded += record["recordedCostUsd"]
        if record["estimatedCostUsd"] is not None:
            estimated += record["estimatedCostUsd"]
    return round(recorded + estimated, 6), round(estimated, 6)


def check_spend_ceiling(
    spent_usd: float,
    limit_usd: Any,
) -> dict[str, Any]:
    """One ceiling against one actual spend figure. ``limit_usd`` from
    config; absent or malformed means no ceiling — ``breached`` is never
    true without a real limit."""
    if not isinstance(limit_usd, (int, float)) or isinstance(limit_usd, bool) or limit_usd < 0:
        return {
            "limitUsd": None,
            "configured": False,
            "breached": False,
            "headroomUsd": None,
            "note": "no ceiling configured",
        }
    limit = float(limit_usd)
    return {
        "limitUsd": limit,
        "configured": True,
        "breached": spent_usd >= limit,
        "headroomUsd": round(limit - spent_usd, 6),
        "note": (
            f"spend {spent_usd:.6f} USD has reached the {limit:.6f} USD ceiling"
            if spent_usd >= limit
            else f"{limit - spent_usd:.6f} USD of ceiling headroom remains"
        ),
    }


def monthly_spend_totals(
    rows: Sequence[Mapping[str, Any]], price: PriceFn | None = None
) -> dict[str, float]:
    """Calendar-month (YYYY-MM) USD totals from token-bearing rows —
    recorded cost plus pack-priced estimates, the same best-known bill
    the ceilings use."""
    totals: dict[str, float] = {}
    for record in spend_records(rows, price):
        if record["periodMonth"] is None:
            continue
        totals[record["periodMonth"]] = round(
            totals.get(record["periodMonth"], 0.0)
            + record["recordedCostUsd"]
            + (record["estimatedCostUsd"] or 0.0),
            6,
        )
    return dict(sorted(totals.items()))


def forecast_monthly_spend(
    monthly_totals: Mapping[str, float],
    current_month: str,
    *,
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> dict[str, Any]:
    """The FR-M39-03 projection, deterministic and documented: an
    ordinary least-squares line over the trailing ``window_months``
    calendar months (zero months included), evaluated at the current
    month. Fewer than two evidence months in the window ->
    ``insufficient_evidence`` and no number."""
    method = (
        f"least-squares line over the trailing {window_months} calendar months "
        "(zero months included), evaluated at the current month"
    )
    trailing: list[float] = []
    year, month = int(current_month[:4]), int(current_month[5:7])
    for _ in range(window_months):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
        label = f"{year:04d}-{month:02d}"
        trailing.append(float(monthly_totals.get(label, 0.0)))
    trailing.reverse()
    evidence_months = sum(1 for value in trailing if value > 0)
    if evidence_months < 2:
        return {
            "status": "insufficient_evidence",
            "projectedUsd": None,
            "slopeUsdPerMonth": None,
            "windowMonths": window_months,
            "evidenceMonths": evidence_months,
            "method": method,
            "note": (
                f"only {evidence_months} of the trailing {window_months} months "
                "carry spend evidence; a projection needs at least two"
            ),
        }
    n = float(len(trailing))
    sum_x = sum(range(len(trailing)))
    sum_y = sum(trailing)
    sum_xx = sum(x * x for x in range(len(trailing)))
    sum_xy = sum(x * y for x, y in enumerate(trailing))
    denominator = n * sum_xx - sum_x * sum_x
    slope = (n * sum_xy - sum_x * sum_y) / denominator if denominator else 0.0
    intercept = (sum_y - slope * sum_x) / n
    projected = intercept + slope * len(trailing)
    return {
        "status": "ok",
        "projectedUsd": round(max(projected, 0.0), 6),
        "slopeUsdPerMonth": round(slope, 6),
        "windowMonths": window_months,
        "evidenceMonths": evidence_months,
        "method": method,
        "note": (
            "projection from the trailing recorded months; a negative "
            "trend floors at zero"
            if projected < 0
            else "projection from the trailing recorded months"
        ),
    }
