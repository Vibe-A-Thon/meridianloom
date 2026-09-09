"""The coverage envelope every analytic result carries (FR-M41-08,
FR-M41-09, NFR-34; N1 Workstream A, D36).

G-01's defect was silent truncation: every analytic asked
``ledger.query`` for exactly 1,000 rows and reported a figure over
whatever came back. The fix is one typed wrapper, returned by every
metric function, that says — in the same operation as the figure, never
a separate call (NFR-34) — how much of the ledger the number actually
saw:

* ``value`` — the headline figure the envelope qualifies (a scalar, or
  null for a multi-figure result or when the metric itself reads
  insufficient_evidence);
* ``rowsConsidered`` — rows of the figure's primary population the
  metric actually examined;
* ``rowsAvailable`` — rows the ledger holds in the metric's declared
  scope (a caller-declared fromSequence/toSequence window counts as
  the available population — a declared window is not truncation);
* ``truncated`` — True when any scan stopped short of its available
  population (the old 1,000-row clamp, now structurally prevented by
  cursor pagination but still disclosed if it ever recurs);
* ``sequenceRange`` — the inclusive [first, last] ledger sequences the
  figure covered (``[None, None]`` over an empty sample);
* ``coverage`` / ``label`` — the explicit ratio considered/available
  and its label: ``complete`` (nothing missed), ``partial`` (some of
  the available population unseen), ``empty`` (nothing available).

D36 (cursor pagination + in-process aggregation) is what makes
``truncated`` rare: :func:`scan_scope` pages the full history through
``ledger.query``'s ``after_sequence`` cursor, so a migrated metric over
an unwindowed scope reports ``truncated: false`` at any ledger size.
The envelope stays because honesty about coverage is the requirement,
not an implementation accident. Auxiliary scans (the rejection-entry
lookups a rate resolves links through) feed :func:`envelope_for` as
``aux_scans`` so a short lookup ALSO marks the figure truncated — a
complete diff population with a capped rejection lookup was exactly the
G-01 shape.

FR-M41-09 at the module level: :func:`forbid_projection` disables any
derived projection over a truncated population and returns the reason
as text.

FR-M41-06 (N1 Workstream B T09): the envelope also carries the
**attribution-coverage dimension** of the figure's population — how many
rows are positively attributable to ``agent`` / ``human`` and how many
are ``unattributed`` (P26: unknown is a state, never a residual).
:class:`AttributionCoverage` rides the envelope under ``attribution``
together with the configurable policy floor (the governance pack's
``attributionCoverageFloor``): when the attributed share falls below the
floor the metric reads ``insufficient_coverage`` and shows no value —
a metric over a population it cannot attribute is not evidence (P25).
:func:`ledger_row_attribution_state` is the documented per-row rule.

FR-M41-13 (N1 Workstream C task 13): the envelope records WHICH
measurement-definitions version produced the figure
(``measurementDefinitions`` — the version string of the record in
``metrics/definitions.py``), so a figure stays attributable to the
definition of its statistic after the definition changes.

FR-M41-12 (N1 Workstream C task 17): data that was intentionally dropped
or is unrecoverable rides the envelope as NAMED gaps (``gaps`` — a
``DataGap`` per class: duplicates, unparseable rows, excluded paths,
unsupported vendors, each with its count). A drop is never an absence:
if ingest dropped rows while producing the population a figure saw, the
figure says so in the same operation (NFR-34).

Zero model calls (FR-M36-07): counting and arithmetic over ledger rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "ATTACH_KEY",
    "ATTACH_KEY_SCORE",
    "AttributionCoverage",
    "CoverageEnvelope",
    "DataGap",
    "INSUFFICIENT_COVERAGE",
    "attribution_coverage",
    "envelope_for",
    "forbid_projection",
    "ledger_row_attribution_state",
    "scan_scope",
]

#: The result-dict key the envelope rides under (FR-M41-08). One key name
#: everywhere, except trust/score: its ``coverage`` key already names the
#: list of score components WITH evidence (FR-M37-03), so the envelope
#: rides under ``coverageEnvelope`` there — same wrapper, documented key.
ATTACH_KEY = "coverage"
ATTACH_KEY_SCORE = "coverageEnvelope"

#: Default page size for full-history scans — the old hard clamp, now
#: just a page on a cursor (FR-M41-07).
DEFAULT_PAGE_SIZE = 1000

_LABEL_COMPLETE = "complete"
_LABEL_PARTIAL = "partial"
_LABEL_EMPTY = "empty"

#: FR-M41-06: the status a metric reads when its population's attribution
#: coverage falls below the configured policy floor — no value is shown.
INSUFFICIENT_COVERAGE = "insufficient_coverage"

#: Ledger actor kinds that are Meridian-native agent actors (the schema's
#: own vocabulary, ledger/schema.py) — positive agent-authorship evidence.
_AGENT_ACTOR_KINDS = frozenset({"orchestrator", "role", "stack", "sub", "xai", "meta"})


def ledger_row_attribution_state(row: Mapping[str, Any]) -> str:
    """The three-state attribution (FR-M41-04) of ONE ledger row, from the
    row's own positive evidence only — ``agent``, ``human``, or
    ``unattributed``; never derived by subtraction:

    * a recorded external agent ``vendor`` (FR-M35-03) -> ``agent``;
    * a Meridian-native agent actor kind (orchestrator|role|stack|sub|
      xai|meta) -> ``agent``;
    * an ``external`` actor with ``telemetry``/``inferred`` observation
      confidence (FR-M35-02) -> ``agent``;
    * anything else carries no positive authorship evidence ->
      ``unattributed``.

    The ledger records agent authorship positively; it has no positive
    human-authorship marker, so human rows read ``unattributed`` until
    the schema grows one — reported, never absorbed into ``agent``.
    """
    vendor = row.get("vendor") or "meridian"
    kind = row.get("actor_kind") or ""
    confidence = row.get("observation_confidence") or "direct"
    if vendor != "meridian":
        return "agent"
    if kind in _AGENT_ACTOR_KINDS:
        return "agent"
    if kind == "external" and confidence in ("telemetry", "inferred"):
        return "agent"
    return "unattributed"


@dataclass(frozen=True)
class AttributionCoverage:
    """FR-M41-06: the attribution-coverage dimension of a figure's
    population, computed in the same operation as the figure (NFR-34)."""

    agent: int
    human: int
    unattributed: int
    coverage: float  # (agent + human) / total; 1.0 over an empty population
    floor: float | None  # the configured policy floor; null = unconfigured
    belowFloor: bool  # coverage < floor over a non-empty population

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "human": self.human,
            "unattributed": self.unattributed,
            "coverage": self.coverage,
            "floor": self.floor,
            "belowFloor": self.belowFloor,
        }


def attribution_coverage(
    states: Sequence[str],
    floor: float | None = None,
) -> AttributionCoverage:
    """The AttributionCoverage over per-row states. An empty population
    covers completely (nothing to attribute, nothing missed) — the
    empty-sample verdict is the metric's own ``insufficient_evidence``.
    ``floor`` outside [0, 1] is ignored (unconfigured)."""
    agent = sum(1 for state in states if state == "agent")
    human = sum(1 for state in states if state == "human")
    total = len(states)
    coverage = round((agent + human) / total, 6) if total else 1.0
    effective_floor: float | None = None
    if (
        isinstance(floor, (int, float))
        and not isinstance(floor, bool)
        and 0.0 <= float(floor) <= 1.0
    ):
        effective_floor = float(floor)
    return AttributionCoverage(
        agent=agent,
        human=human,
        unattributed=total - agent - human,
        coverage=coverage,
        floor=effective_floor,
        belowFloor=bool(
            effective_floor is not None and total > 0 and coverage < effective_floor
        ),
    )


@dataclass(frozen=True)
class DataGap:
    """FR-M41-12: one named class of intentionally dropped or unrecoverable
    data, with its count. ``gapClass`` is a stable vocabulary (duplicate,
    unparseable, excluded_path, unsupported_vendor, ...) shared by the
    event ingester (``meridian_core.ingest``) and every metric surface."""

    gapClass: str
    count: int
    detail: str | None = None  # where it happened, when it helps

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"gapClass": self.gapClass, "count": self.count}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class CoverageEnvelope:
    """The FR-M41-08 disclosure, one typed wrapper for every analytic."""

    value: Any
    rowsConsidered: int
    rowsAvailable: int
    truncated: bool
    sequenceRange: tuple[int | None, int | None]
    coverage: float
    label: str
    # FR-M41-06: the attribution-coverage dimension; None when the metric
    # does not attribute its population (older surfaces stay valid).
    attribution: AttributionCoverage | None = None
    # FR-M41-13: the measurement-definitions version that produced the
    # figure; None on envelopes built before the definitions existed.
    measurementDefinitions: str | None = None
    # FR-M41-12: named dropped/unrecoverable data classes with counts;
    # empty when nothing was dropped (absence of drops is not a gap).
    gaps: tuple[DataGap, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """The wire/JSON shape — camelCase, matching the bus schema's
        CoverageEnvelope $def."""
        payload: dict[str, Any] = {
            "value": self.value,
            "rowsConsidered": self.rowsConsidered,
            "rowsAvailable": self.rowsAvailable,
            "truncated": self.truncated,
            "sequenceRange": [self.sequenceRange[0], self.sequenceRange[1]],
            "coverage": self.coverage,
            "label": self.label,
        }
        if self.attribution is not None:
            payload["attribution"] = self.attribution.to_dict()
        if self.measurementDefinitions is not None:
            payload["measurementDefinitions"] = self.measurementDefinitions
        if self.gaps:
            payload["gaps"] = [gap.to_dict() for gap in self.gaps]
        return payload

    @classmethod
    def empty(
        cls,
        value: Any = None,
        *,
        attribution: AttributionCoverage | None = None,
        measurement_definitions: str | None = None,
        gaps: Sequence[DataGap] = (),
    ) -> "CoverageEnvelope":
        """The envelope over an empty available population: nothing was
        truncated (there was nothing to miss) and the figure reads
        insufficient_evidence upstream — never zero by this wrapper."""
        return cls(
            value=value,
            rowsConsidered=0,
            rowsAvailable=0,
            truncated=False,
            sequenceRange=(None, None),
            coverage=1.0,
            label=_LABEL_EMPTY,
            attribution=attribution,
            measurementDefinitions=measurement_definitions,
            gaps=tuple(gaps),
        )


def envelope_for(
    value: Any,
    primary_rows: Sequence[Mapping[str, Any]],
    primary_available: int,
    aux_scans: Sequence[tuple[Sequence[Mapping[str, Any]], int]] = (),
    attribution_states: Sequence[str] | None = None,
    attribution_floor: float | None = None,
    measurement_definitions: str | None = None,
    data_gaps: Sequence[DataGap] = (),
) -> CoverageEnvelope:
    """The envelope for a figure computed over ``primary_rows`` when the
    ledger holds ``primary_available`` rows in the figure's scope.

    ``aux_scans`` are ``(rows, available)`` pairs for the metric's
    auxiliary lookups (e.g. the rejection entries a rate resolves links
    through): a short auxiliary scan also marks the figure truncated —
    the primary population was complete but the linkage that qualifies
    it was not (the G-01 shape).

    ``attribution_states`` (FR-M41-06) are the per-row three-state
    attributions of the figure's population (see
    :func:`ledger_row_attribution_state`); with ``attribution_floor``
    the envelope's attribution dimension reports whether the attributed
    share fell below the configured policy floor.

    ``measurement_definitions`` (FR-M41-13) is the version string of the
    definitions record that produced the figure.
    ``data_gaps`` (FR-M41-12) are the named dropped/unrecoverable-data
    classes (with counts) incurred while producing the figure's
    population — recorded on the envelope, never silent.

    ``truncated`` is derived, never supplied: fewer examined rows than
    the scope holds means truncation, and the envelope must say so
    (FR-M41-08/09)."""
    considered = len(primary_rows)
    truncated = considered < primary_available or any(
        len(rows) < available for rows, available in aux_scans
    )
    if considered:
        sequences = [int(row["seq"]) for row in primary_rows]
        sequence_range: tuple[int | None, int | None] = (
            min(sequences),
            max(sequences),
        )
    else:
        sequence_range = (None, None)
    attribution = (
        attribution_coverage(attribution_states, attribution_floor)
        if attribution_states is not None
        else None
    )
    if primary_available <= 0:
        return CoverageEnvelope.empty(
            value,
            attribution=attribution,
            measurement_definitions=measurement_definitions,
            gaps=data_gaps,
        )
    return CoverageEnvelope(
        value=value,
        rowsConsidered=considered,
        rowsAvailable=primary_available,
        truncated=truncated,
        sequenceRange=sequence_range,
        coverage=round(considered / primary_available, 6),
        label=_LABEL_PARTIAL if truncated else _LABEL_COMPLETE,
        attribution=attribution,
        measurementDefinitions=measurement_definitions,
        gaps=tuple(data_gaps),
    )


def scan_scope(
    ledger,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    **filters: Any,
) -> tuple[list[dict[str, Any]], int]:
    """The full history for a query scope, cursor-paginated (FR-M41-07,
    D36): pages through ``ledger.query``'s exclusive ``after_sequence``
    cursor until the scope is exhausted. Returns ``(rows,
    rows_available)`` — the rows and the scope's COUNT, the two halves
    every metric's envelope needs, both from this one operation
    (NFR-34). ``filters`` are ``query``/``count`` scope kwargs
    (story_id, actor_id, action_type, from_sequence, ...)."""
    page_size = min(max(int(page_size), 1), DEFAULT_PAGE_SIZE)
    rows_available = ledger.count(**filters)
    rows: list[dict[str, Any]] = []
    after: int | None = None
    while len(rows) < rows_available:
        page = ledger.query(after_sequence=after, limit=page_size, **filters)
        if not page:
            break
        rows.extend(page)
        after = page[-1]["seq"]
        if len(page) < page_size:
            break
    return rows, rows_available


def forbid_projection(envelope: CoverageEnvelope) -> str | None:
    """FR-M41-09 at the module level: a derived projection over a
    truncated population is disabled, and the reason is a string the
    metric can put in its note. ``None`` means the projection may run."""
    if not envelope.truncated:
        return None
    return (
        f"projection disabled: the figure covers {envelope.rowsConsidered} of "
        f"{envelope.rowsAvailable} rows in scope (sequences "
        f"{envelope.sequenceRange[0]}..{envelope.sequenceRange[1]}) — a "
        "forecast over a truncated population would extrapolate a sample "
        "silently (FR-M41-09)"
    )
