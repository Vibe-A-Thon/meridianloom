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

from datetime import datetime, timezone
from typing import Any, Sequence

# Absolute (not relative) so the stdlib-only guard in test_dora_export.py
# can admit this one in-package import by name — the FR-M37-08 rule is "no
# OTLP SDK, no third-party dependency", and metrics.coverage is stdlib
# only (FR-M36-07: zero model calls).
from meridian_core.metrics.coverage import (
    ATTACH_KEY,
    envelope_for,
    scan_scope,
)

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
) -> dict[str, Any]:
    """The four DORA keys over the in-scope ledger rows.

    The result separates ``status`` (ok | unknown per key — unknown is a
    fact about the evidence, never a failure) from ``metrics`` (the values
    and notes), so the caller can render and export honestly.
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

    approved = [row for row in rows if row.get("decision") == "approved"]
    failures = [row for row in approved if row["seq"] in failed_sequences]

    # deployment_frequency: approved changes per calendar week over the
    # observed range (a week inside the range with no deployment counts as
    # zero — the range, not the successes, is the denominator's anchor).
    deployment_frequency: dict[str, Any]
    if approved:
        timestamps = [_parse_ts(row["ts_utc"]) for row in approved]
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
        first_proposed = min(_parse_ts(row["ts_utc"]) for row in story_rows)
        first_approved = min(_parse_ts(row["ts_utc"]) for row in story_approved)
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
            _parse_ts(row["ts_utc"])
        )
    for stamps in approved_by_story.values():
        stamps.sort()
    restore_times: list[float] = []
    for row in failures:
        failed_at = failed_sequences[row["seq"]]
        recovery = [
            ts
            for ts in approved_by_story.get(row["story_id"], [])
            if ts > failed_at
        ]
        if recovery:
            restore_times.append(
                (recovery[0] - failed_at).total_seconds() / 3600
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
        "scope": scope,
        "status": {key: metric["status"] for key, metric in metrics.items()},
        "metrics": metrics,
        # Multi-key result: the envelope carries no single value. AMD-M17:
        # the DORA export carries the FR-M41-08 disclosure like every KPI.
        ATTACH_KEY: envelope_for(
            None,
            scoped_rows,
            rows_available,
            aux_scans=((rejection_scanned, rejection_available),),
        ).to_dict(),
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
            data_point["attributes"] = point_attributes + _otlp_attributes(
                {"meridian.evidence": "unknown"}
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
