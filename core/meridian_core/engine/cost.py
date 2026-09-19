"""Ledger-history cost estimation capability (FR-M33-02; FR-M26-01).

Estimates a new story's cost from the SAME CLASS's recorded ledger
history: rows are normalised through the M39 spend feed
(``metrics/spendfeed.spend_records``), grouped per story, and the
estimate is the median per-story cost with an explicit spread (min,
p25, p75, max) and the sample count. Recorded cost is used where a row
recorded it; the feed's estimated cost (tokens priced through the pack)
is used only where nothing was recorded — the two are never blended
silently.

No same-class history means the answer is ``unknown`` — a valid
deterministic result, never a fabricated number (FR-M39-04).

Zero model calls: arithmetic over ledger rows.
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

from ..metrics.spendfeed import spend_records
from .capabilities import CapabilityOutcome

__all__ = ["LedgerCostEstimateCapability"]

_CAPABILITY_NAME = "ledger_cost_estimate"

#: Rows may carry the class on this key (FR-M26 story classification).
_CLASS_FIELD = "story_class"


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Deterministic linear-interpolation percentile over sorted data."""
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


class LedgerCostEstimateCapability:
    """The ``ledger_cost_estimate`` capability, owned by the
    ``estimate_cost`` action class (FR-M33-01).

    Payload: ``{rows, story_class}`` — ``rows`` are raw ledger rows
    (mappings with token/cost fields and optionally ``story_class``).
    """

    @property
    def name(self) -> str:
        return _CAPABILITY_NAME

    def run(self, action: Mapping[str, Any]) -> CapabilityOutcome:
        rows = action.get("rows")
        if not isinstance(rows, list):
            return CapabilityOutcome(handled=False, reason="missing 'rows' (ledger rows)")
        story_class = action.get("story_class")
        if not isinstance(story_class, str) or not story_class.strip():
            return CapabilityOutcome(handled=False, reason="missing 'story_class'")

        # Per-story cost over same-class rows: recorded first, the priced
        # estimate only where nothing was recorded.
        class_rows = [row for row in rows if row.get(_CLASS_FIELD) == story_class]
        records = [r for r in spend_records(class_rows) if r["story"] is not None]
        per_story: dict[str, float] = {}
        for record in records:
            cost = record["recordedCostUsd"] or (record["estimatedCostUsd"] or 0.0)
            per_story[str(record["story"])] = per_story.get(str(record["story"]), 0.0) + cost

        if not per_story:
            return CapabilityOutcome(
                handled=True,
                result={
                    "story_class": story_class,
                    "status": "unknown",
                    "estimate_usd": None,
                    "reason": "no recorded history for this story class — unknown, never estimated "
                    "without evidence (FR-M39-04)",
                    "sample_count": 0,
                },
                reason="no same-class ledger history (FR-M26-01)",
            )

        costs = sorted(per_story.values())
        median = statistics.median(costs)
        result = {
            "story_class": story_class,
            "status": "estimated",
            "estimate_usd": round(median, 6),
            "spread_usd": {
                "min": round(costs[0], 6),
                "p25": round(_percentile(costs, 0.25), 6),
                "p75": round(_percentile(costs, 0.75), 6),
                "max": round(costs[-1], 6),
            },
            "sample_count": len(costs),
            "basis": "median per-story recorded cost over same-class ledger history",
        }
        return CapabilityOutcome(
            handled=True,
            result=result,
            reason=f"estimated from {len(costs)} same-class stor(ies) (FR-M33-02)",
        )
