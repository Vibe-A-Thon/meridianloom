"""Per-figure statistical disclosure (FR-M41-14; N1 Workstream C task 14).

FR-M41-14: every reported figure SHALL carry its sample count, a
confidence interval where the statistic admits one, and the proportion of
missing data. An empty sample SHALL read ``insufficient_evidence``, never
zero.

Three shapes, one vocabulary:

* **proportions** (rejection rate, first-pass yield) — a Wilson score
  interval at 95% (z = 1.959964). The Wilson interval is the honest
  choice for ledger proportions: it is bounded in [0, 1], behaves at the
  edges (an 0/3 yield shows an upper bound below 1, not a point of 0 with
  no width), and needs no model — closed-form arithmetic over the count
  (zero model calls, FR-M36-07);
* **statistics with no admissible CI** (medians, ratios without a model,
  distributions) — the figure SAYS SO: ``confidenceInterval`` is null and
  ``ciReason`` names why. Omission would read as precision the number
  does not have (P26: unknown is a state, never a residual);
* **empty samples** — ``status`` reads ``insufficient_evidence`` with a
  null value and no interval, extending the honesty state the trust
  components already carry (compare.py, budget.py) — never a fabricated
  zero.

``missingShare`` is the share of the figure's available population that
did not contribute evidence: rows unseen by the scan plus rows the ledger
cannot attribute (unattributed is missing evidence about authorship,
FR-M41-04). It is recorded on every figure, including the empty one.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = [
    "INSUFFICIENT_EVIDENCE",
    "NO_CI_PREFIX",
    "figure_statistics",
    "proportion_statistics",
    "wilson_interval",
]

#: The honesty state an empty sample reads (extends the existing
#: insufficient_evidence vocabulary — compare.py, budget.py, jcurve.py).
INSUFFICIENT_EVIDENCE = "insufficient_evidence"

#: Every explicit no-CI reason starts with this prefix, so a consumer can
#: tell "the statistic admits no interval" apart from "not computed".
NO_CI_PREFIX = "no_confidence_interval"

#: 95% two-sided normal quantile.
_Z95 = 1.959963985004359


def wilson_interval(successes: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """The Wilson score interval for a binomial proportion.

    ``successes`` of ``n`` trials; returns ``(low, high)`` both bounded in
    [0, 1]. Closed-form — no model is fitted over ledger rows.
    Raises ``ValueError`` when ``n`` is not positive: an empty sample has
    no interval, it has a status (``insufficient_evidence``)."""
    if n <= 0:
        raise ValueError("wilson_interval needs a positive sample")
    successes = min(max(int(successes), 0), n)
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    margin = (z / denominator) * math.sqrt(
        (p * (1 - p) + z2 / (4 * n)) / n
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def proportion_statistics(
    successes: int,
    n: int,
    *,
    missing: int = 0,
    available: int | None = None,
) -> dict[str, Any]:
    """The FR-M41-14 disclosure for a binomial proportion figure.

    ``successes``/``n`` parameterise the Wilson interval; ``missing`` is
    the count of the available population that contributed no evidence
    (unseen + unattributed rows). An empty sample reads
    ``insufficient_evidence`` with a null interval — never a zero-width
    or zero-valued CI."""
    population = n if available is None else max(int(available), n)
    missing_share = round(min(max(missing, 0), population) / population, 6) if population else 1.0
    if n <= 0:
        return {
            "status": INSUFFICIENT_EVIDENCE,
            "sampleCount": 0,
            "missingShare": missing_share,
            "confidenceInterval": None,
            "ciReason": (
                "insufficient_evidence: the sample is empty — no interval, "
                "never a zero (FR-M41-14)"
            ),
        }
    low, high = wilson_interval(successes, n)
    return {
        "status": "ok",
        "sampleCount": int(n),
        "missingShare": missing_share,
        "confidenceInterval": {
            "method": "wilson",
            "level": 0.95,
            "low": round(low, 6),
            "high": round(high, 6),
        },
        "ciReason": None,
    }


def figure_statistics(
    sample_count: int,
    *,
    statistic: str,
    missing: int = 0,
    available: int | None = None,
) -> dict[str, Any]:
    """The FR-M41-14 disclosure for a figure whose statistic admits no
    confidence interval (medians, ratios without a model, distributions).

    The absence is stated, not silently omitted: ``confidenceInterval``
    is null and ``ciReason`` names the statistic and the rule. An empty
    sample reads ``insufficient_evidence`` either way."""
    population = (
        sample_count if available is None else max(int(available), sample_count)
    )
    missing_share = (
        round(min(max(missing, 0), population) / population, 6)
        if population
        else 1.0
    )
    if sample_count <= 0:
        return {
            "status": INSUFFICIENT_EVIDENCE,
            "sampleCount": 0,
            "missingShare": missing_share,
            "confidenceInterval": None,
            "ciReason": (
                "insufficient_evidence: the sample is empty (FR-M41-14)"
            ),
        }
    return {
        "status": "ok",
        "sampleCount": int(sample_count),
        "missingShare": missing_share,
        "confidenceInterval": None,
        "ciReason": (
            f"{NO_CI_PREFIX}: {statistic} is not a proportion — no "
            "confidence interval is computed without a model (FR-M41-14)"
        ),
    }
