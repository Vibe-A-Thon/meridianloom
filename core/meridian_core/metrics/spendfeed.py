"""Cross-vendor spend feed (FR-M39-01; F1 Workstream F task 26).

The M39 spend series adapts the ledger's recorded session/token facts onto
the :class:`SpendSeries` protocol from ``metrics/spend.py`` (D26) — the
tokenmaxxing detector and any other consumer read the same interface off
live records instead of caller-supplied fixtures.

Derivation, deliberately simple and auditable:

* a *spend record* is a ledger entry whose ``tokens_in``/``tokens_out``
  or ``cost_usd`` is recorded — one row, one record; nothing is invented;
* *periods* are calendar ISO weeks (``2026-W01``, the labels the
  tokenmaxxing interface matches on) or calendar months (``2026-01``,
  the forecast's unit), chosen per call;
* *tokens* per period are ``tokens_in + tokens_out`` summed per actor;
* *cost* is ``cost_usd`` when the row recorded it. When a row recorded
  tokens but no cost, an optional pricing callable (task 29's pack)
  prices them — recorded cost and estimated cost are reported as
  separate fields, never blended silently;
* *dimensions* — vendor, model, agent, story, team, cost centre. The
  ledger carries vendor/model/agent/story directly; team and cost centre
  resolve through story metadata (FR-M26-03 attribution), read from the
  story-metadata pack (``policy/stories.yaml`` in the repository, a
  workspace override at ``.meridian/policy/stories.yaml``, first readable
  wins — the same convention as the governance pack). A story with no
  metadata evidence lands in the ``unknown`` bucket, and a metadata key
  that is present but empty is also ``unknown`` — dimensions with no
  recorded evidence are unknown, never fabricated.

Zero model calls (FR-M36-07): arithmetic over ledger rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

from .jcurve import parse_utc
from .spend import SpendPoint, SpendSeries

__all__ = [
    "DIMENSIONS",
    "LedgerSpendSeries",
    "StoryMetadata",
    "period_label",
    "spend_by_dimension",
    "spend_records",
]

#: The six FR-M39-01 dimensions.
DIMENSIONS = ("vendor", "model", "agent", "story", "team", "costCentre")

#: The label every dimension without recorded evidence reports under.
UNKNOWN = "unknown"

#: A pricing callable: (vendor, model, tokens_in, tokens_out) -> USD or None.
PriceFn = Callable[[str | None, str | None, int, int], float | None]


def period_label(ts_utc: str | None, granularity: str = "week") -> str | None:
    """The ordered period label for one timestamp: ISO week (2026-W01) or
    calendar month (2026-01). Unparseable timestamps yield None — the row
    still counts in totals, it just cannot sit on a series."""
    parsed = parse_utc(ts_utc)
    if parsed is None:
        return None
    if granularity == "month":
        return f"{parsed.year:04d}-{parsed.month:02d}"
    year, week, _ = parsed.date().isocalendar()
    return f"{year}-W{week:02d}"


def _row_tokens(row: Mapping[str, Any]) -> tuple[int, int]:
    tokens_in = row.get("tokens_in")
    tokens_out = row.get("tokens_out")
    return (
        tokens_in if isinstance(tokens_in, int) else 0,
        tokens_out if isinstance(tokens_out, int) else 0,
    )


def _row_cost(
    row: Mapping[str, Any], price: PriceFn | None
) -> tuple[float, float | None]:
    """(recorded, estimated) cost for one row. ``recorded`` is the row's
    own ``cost_usd`` (0.0 when absent); ``estimated`` is tokens priced
    through the pack when the row recorded no cost (None when there is
    nothing to price or no rate)."""
    recorded = row.get("cost_usd")
    recorded_usd = float(recorded) if isinstance(recorded, (int, float)) else 0.0
    tokens_in, tokens_out = _row_tokens(row)
    estimated: float | None = None
    if price is not None and recorded_usd == 0.0 and (tokens_in or tokens_out):
        estimated = price(row.get("vendor"), row.get("model_id"), tokens_in, tokens_out)
    return recorded_usd, estimated


def spend_records(
    rows: Sequence[Mapping[str, Any]], price: PriceFn | None = None
) -> list[dict[str, Any]]:
    """Normalise ledger rows into spend records: token-bearing rows only,
    each with its recorded and (optionally) estimated cost attached."""
    records: list[dict[str, Any]] = []
    for row in rows:
        tokens_in, tokens_out = _row_tokens(row)
        recorded_usd, estimated_usd = _row_cost(row, price)
        if not (tokens_in or tokens_out or recorded_usd):
            continue
        records.append(
            {
                "seq": row.get("seq"),
                "actor": row.get("actor_id"),
                "story": row.get("story_id"),
                "vendor": row.get("vendor") or "meridian",
                "model": row.get("model_id"),
                "sessionId": row.get("external_session_id"),
                "periodWeek": period_label(row.get("ts_utc"), "week"),
                "periodMonth": period_label(row.get("ts_utc"), "month"),
                "tokensIn": tokens_in,
                "tokensOut": tokens_out,
                "tokens": tokens_in + tokens_out,
                "recordedCostUsd": recorded_usd,
                "estimatedCostUsd": estimated_usd,
            }
        )
    return records


class LedgerSpendSeries(SpendSeries):
    """The M39 feed: ledger spend records adapted onto the SpendSeries
    protocol (D26). ``trust/tokenmaxxing`` can consume this directly —
    periods are the ISO-week labels its yield derivation matches on."""

    def __init__(self, rows: Sequence[Mapping[str, Any]], price: PriceFn | None = None):
        self._by_agent: dict[str, dict[str, float]] = {}
        for record in spend_records(rows, price):
            if record["actor"] is None or record["periodWeek"] is None:
                continue
            periods = self._by_agent.setdefault(str(record["actor"]), {})
            periods[record["periodWeek"]] = (
                periods.get(record["periodWeek"], 0.0) + record["tokens"]
            )

    def points(self, agent_id: str) -> Sequence[SpendPoint]:
        periods = self._by_agent.get(agent_id, {})
        return [
            SpendPoint(period=period, tokens=tokens)
            for period, tokens in sorted(periods.items())
        ]

    def agents(self) -> Sequence[str]:
        return sorted(self._by_agent)


@dataclass
class StoryMetadata:
    """Story -> {team, costCentre} attribution (FR-M26-03), parsed
    fail-closed from the story-metadata pack exactly like the governance
    pack: any schema error lands in ``errors`` and every lookup reports
    unknown — a malformed pack never fabricates attribution."""

    source: str = "story-metadata"
    entries: dict[str, dict[str, str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def fail_closed(self) -> bool:
        return bool(self.errors)

    def lookup(self, story_id: str | None) -> dict[str, str]:
        """team/costCentre for a story; missing evidence is 'unknown'."""
        if story_id and story_id in self.entries:
            return self.entries[story_id]
        wildcard = self.entries.get("*")
        if wildcard is not None:
            return wildcard
        return {"team": UNKNOWN, "costCentre": UNKNOWN}


def parse_story_metadata(text: str, source: str) -> StoryMetadata:
    """Parse one story-metadata pack document. Never raises on content."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return StoryMetadata(source=source, errors=[f"{source}: not valid YAML: {error}"])
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        return StoryMetadata(
            source=source, errors=[f"{source}: must be a mapping at the top level"]
        )
    unknown = set(raw) - {"version", "stories"}
    errors = [f"{name}: unknown top-level section" for name in sorted(unknown)]
    version = raw.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        errors.append(f"version: expected an integer >= 1, got {version!r}")
    entries: dict[str, dict[str, str]] = {}
    stories = raw.get("stories", {})
    if not isinstance(stories, Mapping):
        errors.append("stories: expected a mapping of storyId to metadata")
    else:
        for story_id, meta in stories.items():
            where = f"stories.{story_id}"
            if not isinstance(story_id, str) or not story_id.strip():
                errors.append("stories: story ids must be non-empty strings")
                continue
            if not isinstance(meta, Mapping):
                errors.append(f"{where}: expected a mapping with team/costCentre")
                continue
            unknown_keys = set(meta) - {"team", "costCentre"}
            for key in sorted(unknown_keys):
                errors.append(f"{where}: unknown key {key}")
            entry: dict[str, str] = {}
            for key in ("team", "costCentre"):
                value = meta.get(key)
                if value is None:
                    entry[key] = UNKNOWN
                elif isinstance(value, str) and value.strip():
                    entry[key] = value.strip()
                else:
                    errors.append(f"{where}.{key}: expected a non-empty string")
                    entry[key] = UNKNOWN
            entries[story_id.strip()] = entry
    if errors:
        return StoryMetadata(source=source, errors=[f"{source}: {e}" for e in errors])
    return StoryMetadata(source=source, entries=entries)


def load_story_metadata(paths: Sequence[str | Path]) -> StoryMetadata:
    """First readable file wins (workspace override, then repository
    default). No readable file yields an empty pack — every story
    reports unknown, never an exception."""
    tried: list[str] = []
    for path in paths:
        candidate = Path(path)
        tried.append(str(candidate))
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        return parse_story_metadata(text, str(candidate))
    return StoryMetadata(source="story-metadata", entries={})


def _bucket() -> dict[str, Any]:
    return {
        "entries": 0,
        "tokensIn": 0,
        "tokensOut": 0,
        "tokens": 0,
        "recordedCostUsd": 0.0,
        "estimatedCostUsd": 0.0,
        "costEstimateCount": 0,
    }


def _add(bucket: dict[str, Any], record: Mapping[str, Any]) -> None:
    bucket["entries"] += 1
    bucket["tokensIn"] += record["tokensIn"]
    bucket["tokensOut"] += record["tokensOut"]
    bucket["tokens"] += record["tokens"]
    bucket["recordedCostUsd"] = round(
        bucket["recordedCostUsd"] + record["recordedCostUsd"], 6
    )
    if record["estimatedCostUsd"] is not None:
        bucket["estimatedCostUsd"] = round(
            bucket["estimatedCostUsd"] + record["estimatedCostUsd"], 6
        )
        bucket["costEstimateCount"] += 1


def _finish(bucket: dict[str, Any]) -> dict[str, Any]:
    bucket["recordedCostUsd"] = round(bucket["recordedCostUsd"], 6)
    bucket["estimatedCostUsd"] = round(bucket["estimatedCostUsd"], 6)
    # costUsd is the honest best-known bill: recorded where recorded,
    # priced where priced, both summed where both exist on different rows.
    bucket["costUsd"] = round(
        bucket["recordedCostUsd"] + bucket["estimatedCostUsd"], 6
    )
    return bucket


def spend_by_dimension(
    rows: Sequence[Mapping[str, Any]],
    dimension: str,
    *,
    story_meta: StoryMetadata | None = None,
    price: PriceFn | None = None,
) -> dict[str, Any]:
    """The FR-M39-01 bill: spend aggregated over one of the six
    dimensions. ``vendor``/``model``/``agent``/``story`` read the ledger
    row; ``team``/``costCentre`` resolve through story metadata and
    report ``unknown`` without evidence — never fabricated."""
    if dimension not in DIMENSIONS:
        raise ValueError(
            f"dimension must be one of {', '.join(DIMENSIONS)}, got {dimension!r}"
        )
    meta = story_meta or StoryMetadata()
    by_value: dict[str, dict[str, Any]] = {}
    totals = _bucket()
    for record in spend_records(rows, price):
        if dimension == "vendor":
            value = str(record["vendor"])
        elif dimension == "model":
            value = str(record["model"]) if record["model"] else UNKNOWN
        elif dimension == "agent":
            value = str(record["actor"]) if record["actor"] else UNKNOWN
        elif dimension == "story":
            value = str(record["story"]) if record["story"] else UNKNOWN
        else:
            key = "team" if dimension == "team" else "costCentre"
            value = meta.lookup(record["story"] if record["story"] else None)[key]
        _add(by_value.setdefault(value, _bucket()), record)
        _add(totals, record)
    return {
        "dimension": dimension,
        "totals": _finish(totals),
        "byValue": {value: _finish(bucket) for value, bucket in sorted(by_value.items())},
    }
