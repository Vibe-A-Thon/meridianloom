"""The adoption J-curve (FR-M37-05; F1 Workstream E task 23).

FR-M37-05: the team-level throughput and stability before and after
adoption, so the initial productivity dip DORA documents is visible as a
phase rather than mistaken for failure. Derived from the ledger on demand
(FR-M17-05 — no metrics database), cached in-process, invalidated on
append, split greenfield/brownfield (G6) — the same conventions as the
other trust metrics.

Definitions, kept honest about what the ledger carries:

* **throughput** — in-scope proposed changes (``diff`` entries) per
  calendar week. Weeks with no diffs count as zero: the dip IS the empty
  weeks, and hiding them would erase the phase this metric exists to
  show;
* **stability** — the F0 rejection notion (the sequence is carried by a
  ``rejection`` entry OR the entry's own decision is
  ``rejected``/``reworked`), reported as a rate per phase;
* **baseline** — mean weekly throughput over the before weeks;
* **the dip** — the contiguous run of below-baseline after-adoption weeks
  starting at the adoption week itself (the dip is only a dip when it
  begins where the change began; a slump a quarter later is not the
  J-curve); ``depth`` is the minimum weekly throughput inside the dip
  relative to baseline; ``recoveredWeek`` is the first week back at or
  above baseline (null when not yet recovered — an unrecovered dip is a
  fact, not a failure to compute);
* **insufficient evidence** — no in-scope diffs at all: the sample is
  empty and every aggregate stays null, never zero. Diffs on only one
  side of the adoption date report ``partial``.

Zero model calls (FR-M36-07): calendar arithmetic over ledger rows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

__all__ = ["compute_jcurve", "parse_utc"]

GREENFIELD = "greenfield"
BROWNFIELD = "brownfield"
UNCLASSIFIED = "unclassified"

REJECTED_DECISIONS = ("rejected", "reworked")

_STATUS_OK = "ok"
_STATUS_PARTIAL = "partial"
_STATUS_INSUFFICIENT = "insufficient_evidence"


def parse_utc(ts_utc: str | None) -> datetime | None:
    """One tolerant ISO-8601 parser shared by the time-bucketed metrics."""
    if not ts_utc:
        return None
    try:
        return datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_ts(ts_utc: str | None) -> datetime | None:
    return parse_utc(ts_utc)


def _week_monday(day: date) -> date:
    return day.fromordinal(day.toordinal() - day.weekday())


def _phase_stats(
    weekly: dict[int, int], weeks: list[int], rejected: int, proposed: int
) -> dict[str, Any]:
    total = sum(weekly.get(w, 0) for w in weeks)
    return {
        "weeks": len(weeks),
        "weeklyThroughput": {str(w): weekly.get(w, 0) for w in weeks},
        "throughputPerWeek": round(total / len(weeks), 6) if weeks else None,
        "proposed": proposed,
        "rejected": rejected,
        "stabilityRate": round(rejected / proposed, 6) if proposed else None,
    }


def compute_jcurve(
    ledger,
    *,
    adoption_date: str | datetime,
    repo_id: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    classify: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """The FR-M37-05 J-curve for the adoption cut ``adoption_date``.

    ``classify`` maps a story id to GREENFIELD/BROWNFIELD or None
    (unclassified); absent entirely, everything lands in unclassified.
    """
    scope = {
        "adoptionDate": adoption_date
        if isinstance(adoption_date, str)
        else adoption_date.isoformat(),
        "repoId": repo_id,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }
    adoption = _parse_ts(scope["adoptionDate"])
    if adoption is None:
        raise ValueError(f"unparseable adoptionDate: {scope['adoptionDate']!r}")
    adoption_monday = _week_monday(adoption.date())

    rows = ledger.query(
        action_type="diff",
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        limit=1000,
    )
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]
    rows = [row for row in rows if _parse_ts(row.get("ts_utc")) is not None]

    rejection_rows = ledger.query(action_type="rejection", limit=1000)
    if repo_id is not None:
        rejection_rows = [
            row for row in rejection_rows if row.get("repo_id") == repo_id
        ]
    if from_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] >= from_sequence
        ]
    if to_sequence is not None:
        rejection_rows = [
            row for row in rejection_rows if row["seq"] <= to_sequence
        ]
    rejected_sequences = {
        row["rejected_sequence"]
        for row in rejection_rows
        if row.get("rejected_sequence") is not None
    }

    def is_rejected(row: dict[str, Any]) -> bool:
        return row["seq"] in rejected_sequences or row.get("decision") in (
            REJECTED_DECISIONS
        )

    # Bucket every in-scope diff into its relative week (adoption week = 0).
    weekly: dict[int, int] = {}
    split_weekly: dict[str, dict[int, int]] = {
        GREENFIELD: {},
        BROWNFIELD: {},
        UNCLASSIFIED: {},
    }
    split_counts: dict[str, dict[str, int]] = {
        kind: {
            "beforeProposed": 0,
            "beforeRejected": 0,
            "afterProposed": 0,
            "afterRejected": 0,
        }
        for kind in split_weekly
    }
    for row in rows:
        ts = _parse_ts(row.get("ts_utc"))
        assert ts is not None  # filtered above
        rel = (_week_monday(ts.date()) - adoption_monday).days // 7
        weekly[rel] = weekly.get(rel, 0) + 1
        if classify is None:
            kind = UNCLASSIFIED
        else:
            kind = classify(row["story_id"]) or UNCLASSIFIED
            if kind not in split_weekly:
                kind = UNCLASSIFIED
        bucket = split_weekly[kind]
        bucket[rel] = bucket.get(rel, 0) + 1
        counts = split_counts[kind]
        side = "before" if rel < 0 else "after"
        counts[f"{side}Proposed"] += 1
        if is_rejected(row):
            counts[f"{side}Rejected"] += 1

    if not rows:
        return {
            "scope": scope,
            "adoptionDate": scope["adoptionDate"],
            "status": _STATUS_INSUFFICIENT,
            "baseline": None,
            "dip": {},
            "phases": {"before": None, "after": None},
            "split": {
                kind: {"before": None, "after": None} for kind in split_weekly
            },
        }

    # Calendar filling: a week inside the observed span with no diffs is a
    # real week at zero throughput — the dip IS the empty weeks. Before
    # spans the first observed before-week .. -1; after spans 0 .. last.
    observed_before = [w for w in weekly if w < 0]
    observed_after = [w for w in weekly if w >= 0]
    before_weeks = list(range(min(observed_before), 0)) if observed_before else []
    after_weeks = list(range(0, max(observed_after) + 1)) if observed_after else []
    baseline = (
        round(
            sum(weekly.get(w, 0) for w in before_weeks) / len(before_weeks), 6
        )
        if before_weeks
        else None
    )

    # The dip: contiguous below-baseline after-weeks from week 0. Only
    # calendar weeks between the first and last observed after-week are
    # considered — an empty ledger tail is "not recovered yet", not "still
    # dipping forever"; an empty observed week inside the range counts as
    # zero throughput and extends the dip.
    dip: dict[str, Any] = {}
    if after_weeks and baseline:
        observed = set(after_weeks)
        run: list[int] = []
        week = 0
        last_observed = max(after_weeks)
        while week <= last_observed:
            if weekly.get(week, 0) < baseline:
                run.append(week)
            else:
                break
            week += 1
        if run:
            recovered = None
            probe = max(run) + 1
            while probe <= last_observed:
                if probe in observed and weekly.get(probe, 0) >= baseline:
                    recovered = probe
                    break
                probe += 1
            dip = {
                "startWeek": run[0],
                "endWeek": run[-1],
                "depth": round((min(weekly.get(w, 0) for w in run) - baseline) / baseline, 6),
                "recoveredWeek": recovered,
            }

    before_proposed = sum(weekly.get(w, 0) for w in before_weeks)
    before_rejected = sum(
        1
        for row in rows
        if _parse_ts(row.get("ts_utc")) is not None
        and (_week_monday(_parse_ts(row.get("ts_utc")).date()) - adoption_monday).days // 7 < 0
        and is_rejected(row)
    )
    after_proposed = sum(weekly.get(w, 0) for w in after_weeks)
    after_rejected = sum(
        1
        for row in rows
        if _parse_ts(row.get("ts_utc")) is not None
        and (_week_monday(_parse_ts(row.get("ts_utc")).date()) - adoption_monday).days // 7 >= 0
        and is_rejected(row)
    )

    def phase(weeks: list[int], proposed: int, rejected: int) -> dict[str, Any] | None:
        if not weeks:
            return None
        return _phase_stats(weekly, weeks, rejected, proposed)

    status = (
        _STATUS_OK
        if before_weeks and after_weeks
        else _STATUS_PARTIAL
    )

    split_result: dict[str, dict[str, Any]] = {}
    for kind, bucket in split_weekly.items():
        kind_before_observed = [w for w in bucket if w < 0]
        kind_after_observed = [w for w in bucket if w >= 0]
        kind_before = (
            list(range(min(kind_before_observed), 0))
            if kind_before_observed
            else []
        )
        kind_after = (
            list(range(0, max(kind_after_observed) + 1))
            if kind_after_observed
            else []
        )
        counts = split_counts[kind]
        before_total = sum(bucket.get(w, 0) for w in kind_before)
        after_total = sum(bucket.get(w, 0) for w in kind_after)
        split_result[kind] = {
            "before": (
                _phase_stats(
                    bucket, kind_before, counts["beforeRejected"], before_total
                )
                if kind_before
                else None
            ),
            "after": (
                _phase_stats(
                    bucket, kind_after, counts["afterRejected"], after_total
                )
                if kind_after
                else None
            ),
            "proposed": counts["beforeProposed"] + counts["afterProposed"],
            "rejected": counts["beforeRejected"] + counts["afterRejected"],
        }

    return {
        "scope": scope,
        "adoptionDate": scope["adoptionDate"],
        "status": status,
        "baseline": baseline,
        "dip": dip,
        "phases": {
            "before": phase(before_weeks, before_proposed, before_rejected),
            "after": phase(after_weeks, after_proposed, after_rejected),
        },
        "split": split_result,
    }
