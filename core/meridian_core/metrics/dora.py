"""DORA four-keys export in OTLP-friendly JSON (FR-M37-08; F1 Workstream E
task 25).

FR-M37-08: the trust metrics land where leadership already looks — a
DORA-compatible export over the OTLP/JSON metrics mapping, so the payload
drops into an OTLP/HTTP endpoint or the team's engineering-intelligence
tooling unchanged. **Python standard library only** — no OTLP SDK, no
third-party dependency; the encoding is built here from the OTLP/JSON
mapping (resourceMetrics -> scopeMetrics -> metrics -> gauge -> data
points with OTel attribute encoding).

The four keys, derived from the ledger (FR-M17-05 — no metrics database),
with honest proxies where the ledger's vocabulary is smaller than DORA's:

* **deployment frequency** — the ledger records no deploy event type, so
  *deployments* are the approved-change shape: ``diff`` entries whose
  decision is ``approved`` (a change that passed review), counted per
  calendar week. The proxy is documented in the export, never silently
  substituted;
* **lead time for changes** — median hours from a story's first in-scope
  ``diff`` to that story's first ``approved`` diff. A story approved
  without a preceding diff carries no lead time and is not counted;
* **change failure rate** — approved diffs later carried by a
  ``rejection`` entry (the F0 post-merge revert shape) over all approved
  diffs;
* **time to restore** — for each failed change, hours from the earliest
  rejection entry carrying it to the next ``approved`` diff on the same
  story; the median over failures. No failures, or no failure ever
  recovered, is **unknown** — never an invented number.

Unknown keys export a data point carrying ``meridian.evidence = unknown``
and **no value** — an OTLP consumer sees the gap explicitly instead of a
fabricated zero.

Zero model calls (FR-M36-07): datetime arithmetic and JSON-shaped dicts.
"""

from __future__ import annotations

from collections.abc import Callable
from bisect import bisect_right
from datetime import datetime, timezone
from typing import Any, Sequence

# Absolute (not relative) so the stdlib-only guard in test_dora_export.py
# can admit this one in-package import by name — the FR-M37-08 rule is "no
# OTLP SDK, no third-party dependency", and metrics.coverage is stdlib
# only (FR-M36-07: zero model calls).
from meridian_core.metrics.coverage import (
    ATTACH_KEY,
    INSUFFICIENT_COVERAGE,
    attribution_coverage,
    envelope_for,
    ledger_row_attribution_state,
    scan_scope,
)
from meridian_core.metrics.trust import BROWNFIELD, GREENFIELD, UNCLASSIFIED

__all__ = ["compute_dora_metrics", "export_otlp"]

_SECONDS_PER_WEEK = 7 * 24 * 3600

#: DORA key -> (OTLP metric name, unit, description). The descriptions
#: carry the proxy notes so the export is self-documenting downstream.
_METRIC_DEFS = {
    "deploymentFrequency": (
        "dora.deployment_frequency",
        "{deployment}/wk",
        "Approved changes (the ledger records no deploy event type; "
        "approved diffs are the deployment proxy) per calendar week.",
    ),
    "leadTimeForChanges": (
        "dora.lead_time_for_changes",
        "h",
        "Median hours from a story's first in-scope diff to its first "
        "approved diff.",
    ),
    "changeFailureRate": (
        "dora.change_failure_rate",
        "1",
        "Approved diffs later carried by a rejection entry (post-merge "
        "failure shape) over all approved diffs.",
    ),
    "timeToRestore": (
        "dora.time_to_restore",
        "h",
        "Median hours from a failed change's earliest covering rejection "
        "to the story's next approved diff.",
    ),
}

_DEFAULT_RESOURCE_ATTRIBUTES = {
    "service.name": "meridian-loom",
    "service.namespace": "trust-metrics",
}


def _ts_cache(rows: list[dict[str, Any]]) -> dict[int, datetime]:
    """Parse each row's timestamp exactly once, keyed by ledger sequence.

    NFR-33 (D36 continued): AMD-M37 made the greenfield/brownfield split a
    real computation per bucket, so `_dora_for` now runs four times over the
    same population — and each run re-parsed every timestamp it touched, in
    several places. Over a 50k ledger that pushed trust/doraExport from 2.6s
    to over 7s, past the 5s budget. The parse is the hot cost, and it is
    pure: do it once here and hand the result down.

    Keyed by sequence rather than memoised onto the row, so nothing is
    written back into dicts the caller owns.
    """
    cache: dict[int, datetime] = {}
    for row in rows:
        parsed = _parse_ts(row.get("ts_utc"))
        if parsed is not None:
            cache[row["seq"]] = parsed
    return cache


def _parse_ts(ts_utc: str | None) -> datetime | None:
    if not ts_utc:
        return None
    try:
        return datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    except ValueError:
        return None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def compute_dora_metrics(
    ledger,
    *,
    repo_id: str | None = None,
    from_sequence: int | None = None,
    to_sequence: int | None = None,
    attribution_floor: float | None = None,
    classify: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """The four DORA keys over the in-scope ledger rows.

    The result separates ``status`` (ok | unknown per key — unknown is a
    fact about the evidence, never a failure) from ``metrics`` (the values
    and notes), so the caller can render and export honestly.

    FR-M41-06: ``attribution_floor`` (the governance pack's
    ``attributionCoverageFloor``, plumbed by the RPC layer) suppresses
    every key — all read ``insufficient_coverage`` with no value — when
    the attributed share of the diff population falls below the floor.

    AMD-M37 (G6): ``classify`` maps a story id to greenfield/brownfield
    (or None); the export carries the split like every other trust
    metric, each bucket a full four-keys computation over that
    population. Stories the classifier declines land in ``unclassified``,
    reported, never dropped.
    """
    scope = {
        "repoId": repo_id,
        "fromSequence": from_sequence,
        "toSequence": to_sequence,
    }
    # FR-M41-07 (D36): full-history cursor scans; the repo filter below is
    # a declared scope restriction, so the envelope keeps the whole
    # scanned diff population (FR-M41-08). The rejection lookup is the
    # auxiliary scan: a capped lookup truncates the export too.
    rows, rows_available = scan_scope(
        ledger,
        action_type="diff",
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )
    scoped_rows = rows
    if repo_id is not None:
        rows = [row for row in rows if row.get("repo_id") == repo_id]
    rows = [row for row in rows if _parse_ts(row.get("ts_utc")) is not None]

    rejection_rows, rejection_available = scan_scope(
        ledger, action_type="rejection"
    )
    rejection_scanned = rejection_rows
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
    rejection_rows = [
        row for row in rejection_rows if _parse_ts(row.get("ts_utc")) is not None
    ]

    failed_sequences: dict[int, datetime] = {}
    for row in rejection_rows:
        rejected_sequence = row.get("rejected_sequence")
        if rejected_sequence is None:
            continue
        ts = _parse_ts(row.get("ts_utc"))
        prior = failed_sequences.get(rejected_sequence)
        if prior is None or ts < prior:
            failed_sequences[rejected_sequence] = ts

    ts_by_seq = _ts_cache(rows)
    computed = _dora_for(rows, failed_sequences, ts_by_seq)
    metrics = computed["metrics"]

    # AMD-M37 (G6): the split rides the export like every other trust
    # metric — one full four-keys computation per bucket over that
    # bucket's rows.
    split_rows: dict[str, list[dict[str, Any]]] = {
        GREENFIELD: [],
        BROWNFIELD: [],
        UNCLASSIFIED: [],
    }
    for row in rows:
        kind = (
            UNCLASSIFIED
            if classify is None
            else (classify(row["story_id"]) or UNCLASSIFIED)
        )
        if kind not in split_rows:
            kind = UNCLASSIFIED
        split_rows[kind].append(row)
    split: dict[str, dict[str, Any]] = {}
    for kind, bucket_rows in split_rows.items():
        bucket = _dora_for(bucket_rows, failed_sequences, ts_by_seq)
        split[kind] = {
            "status": bucket["status"],
            "metrics": bucket["metrics"],
            "sampleSize": len(bucket_rows),
        }

    # FR-M41-06: below the configured attribution-coverage floor no key is
    # evidence — every value reads insufficient_coverage and shows no
    # value (the OTLP export then carries the status, not a number).
    row_states = [ledger_row_attribution_state(row) for row in rows]
    coverage_check = attribution_coverage(row_states, attribution_floor)
    if coverage_check.belowFloor:
        for metric in metrics.values():
            metric["status"] = INSUFFICIENT_COVERAGE
            metric["value"] = None
            metric["note"] = (
                "attribution coverage below the configured floor "
                f"({coverage_check.coverage} < {coverage_check.floor}) "
                "— insufficient_coverage, no value shown (FR-M41-06)"
            )

    return {
        "scope": scope,
        "status": {key: metric["status"] for key, metric in metrics.items()},
        "metrics": metrics,
        "split": split,
        # Multi-key result: the envelope carries no single value. AMD-M17:
        # the DORA export carries the FR-M41-08 disclosure like every KPI.
        ATTACH_KEY: envelope_for(
            None,
            scoped_rows,
            rows_available,
            aux_scans=((rejection_scanned, rejection_available),),
            attribution_states=row_states,
            attribution_floor=attribution_floor,
        ).to_dict(),
    }


def _dora_for(
    rows: list[dict[str, Any]],
    failed_sequences: dict[int, datetime],
    ts_by_seq: dict[int, datetime],
) -> dict[str, Any]:
    """The four DORA keys over ONE population of diff rows (the headline
    population or one greenfield/brownfield split bucket — AMD-M37)."""
    approved = [row for row in rows if row.get("decision") == "approved"]
    failures = [row for row in approved if row["seq"] in failed_sequences]

    # deployment_frequency: approved changes per calendar week over the
    # observed range (a week inside the range with no deployment counts as
    # zero — the range, not the successes, is the denominator's anchor).
    deployment_frequency: dict[str, Any]
    if approved:
        timestamps = [ts_by_seq[row["seq"]] for row in approved]
        mondays = []
        for ts in timestamps:
            day = ts.date()
            mondays.append(day.fromordinal(day.toordinal() - day.weekday()))
        first_monday = min(mondays)
        per_week: dict[int, int] = {}
        for monday in mondays:
            per_week[(monday - first_monday).days // 7] = (
                per_week.get((monday - first_monday).days // 7, 0) + 1
            )
        span_weeks = max(per_week) + 1
        value = round(sum(per_week.values()) / span_weeks, 6)
        deployment_frequency = {
            "status": "ok",
            "value": value,
            "deployments": len(approved),
            "spanWeeks": span_weeks,
            "note": "approved diffs as the deployment proxy "
            "(the ledger records no deploy event type)",
        }
    else:
        deployment_frequency = {
            "status": "unknown",
            "value": None,
            "deployments": 0,
            "spanWeeks": 0,
            "note": "no approved changes in scope — the ledger records "
            "no deployments to count",
        }

    # lead_time_for_changes: median story first-diff -> first-approved
    # hours. Rows are grouped by story once (NFR-33: no per-story
    # re-scan of the whole population).
    rows_by_story: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_story.setdefault(row["story_id"], []).append(row)
    lead_times: list[float] = []
    for story_id in {row["story_id"] for row in approved}:
        story_rows = rows_by_story[story_id]
        story_approved = [
            row for row in story_rows if row.get("decision") == "approved"
        ]
        if not story_approved:
            continue
        first_proposed = min(ts_by_seq[row["seq"]] for row in story_rows)
        first_approved = min(ts_by_seq[row["seq"]] for row in story_approved)
        if first_approved > first_proposed:
            lead_times.append(
                (first_approved - first_proposed).total_seconds() / 3600
            )
    lead_time = _median(lead_times)
    lead_time_for_changes = (
        {
            "status": "ok",
            "value": round(lead_time, 6),
            "stories": len(lead_times),
            "note": "median hours from a story's first in-scope diff to "
            "its first approved diff",
        }
        if lead_times
        else {
            "status": "unknown",
            "value": None,
            "stories": 0,
            "note": "no approved change follows an in-scope diff — "
            "nothing to time",
        }
    )

    if approved:
        change_failure_rate = {
            "status": "ok",
            "value": round(len(failures) / len(approved), 6),
            "failed": len(failures),
            "deployments": len(approved),
            "note": "approved diffs later carried by a rejection entry",
        }
    else:
        change_failure_rate = {
            "status": "unknown",
            "value": None,
            "failed": 0,
            "deployments": 0,
            "note": "no approved changes in scope",
        }

    # time_to_restore: failure -> the story's next approved diff.
    # NFR-33 (D36): timestamps are parsed once and approved diffs grouped
    # by story up front — the naive failures x approved scan re-parsed a
    # timestamp per comparison and took a minute over a 50k ledger.
    approved_by_story: dict[str, list[datetime]] = {}
    for row in approved:
        approved_by_story.setdefault(row["story_id"], []).append(
            ts_by_seq[row["seq"]]
        )
    for story_stamps in approved_by_story.values():
        story_stamps.sort()
    restore_times: list[float] = []
    for row in failures:
        failed_at = failed_sequences[row["seq"]]
        # NFR-33: these stamps are sorted above, and only the FIRST one after
        # the failure is wanted. Building a filtered list of the whole tail to
        # take its head cost 5.7s of an 11.7s 50k export — the single largest
        # cost in the whole computation. bisect finds the same element without
        # allocating anything.
        story_stamps = approved_by_story.get(row["story_id"], ())
        index = bisect_right(story_stamps, failed_at)
        if index < len(story_stamps):
            restore_times.append(
                (story_stamps[index] - failed_at).total_seconds() / 3600
            )
    restore = _median(restore_times)
    time_to_restore = (
        {
            "status": "ok",
            "value": round(restore, 6),
            "failures": len(restore_times),
            "note": "median hours from a failure's earliest covering "
            "rejection to the story's next approved diff",
        }
        if restore_times
        else {
            "status": "unknown",
            "value": None,
            "failures": 0,
            "note": "no failed change was ever followed by a new approval "
            "— nothing to time",
        }
    )

    metrics = {
        "deploymentFrequency": deployment_frequency,
        "leadTimeForChanges": lead_time_for_changes,
        "changeFailureRate": change_failure_rate,
        "timeToRestore": time_to_restore,
    }
    return {
        "status": {key: metric["status"] for key, metric in metrics.items()},
        "metrics": metrics,
    }


def _otlp_attributes(mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"key": key, "value": {"stringValue": value}}
        for key, value in sorted(mapping.items())
    ]


def export_otlp(
    computed: dict[str, Any],
    *,
    exported_at: str | None = None,
    resource_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The OTLP/JSON encoding of :func:`compute_dora_metrics` output.

    Unknown keys export one data point carrying ``meridian.evidence =
    unknown`` and no value; evidenced keys export ``asDouble`` with the
    note as a point attribute. ``exported_at`` (ISO 8601 UTC) keeps the
    export deterministic under tests; absent means now.
    """
    ts = exported_at or datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
        ).replace("+00:00", "Z")
    stamp = _parse_ts(ts)
    time_unix_nano = str(int(stamp.timestamp() * 1_000_000_000))

    attributes = dict(_DEFAULT_RESOURCE_ATTRIBUTES)
    if resource_attributes:
        attributes.update({str(k): str(v) for k, v in resource_attributes.items()})

    otlp_metrics = []
    for key, metric in sorted(computed["metrics"].items()):
        name, unit, description = _METRIC_DEFS[key]
        point_attributes = _otlp_attributes(
            {"meridian.dora.key": key, "meridian.dora.note": metric["note"]}
        )
        data_point: dict[str, Any] = {
            "attributes": point_attributes,
            "timeUnixNano": time_unix_nano,
        }
        if metric["status"] == "ok":
            data_point["asDouble"] = metric["value"]
        else:
            # insufficient_coverage exports its status too — an OTLP
            # consumer sees WHY the value is missing (FR-M41-06).
            data_point["attributes"] = point_attributes + _otlp_attributes(
                {"meridian.evidence": metric["status"]}
            )
        otlp_metrics.append(
            {
                "name": name,
                "description": description,
                "unit": unit,
                "gauge": {"dataPoints": [data_point]},
            }
        )

    return {
        "resourceMetrics": [
            {
                "resource": {"attributes": _otlp_attributes(attributes)},
                "scopeMetrics": [
                    {
                        "scope": {"name": "meridian.trust"},
                        "metrics": otlp_metrics,
                    }
                ],
            }
        ]
    }
