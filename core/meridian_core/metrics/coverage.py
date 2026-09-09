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

Zero model calls (FR-M36-07): counting and arithmetic over ledger rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "ATTACH_KEY",
    "ATTACH_KEY_SCORE",
    "CoverageEnvelope",
    "envelope_for",
    "forbid_projection",
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

    def to_dict(self) -> dict[str, Any]:
        """The wire/JSON shape — camelCase, matching the bus schema's
        CoverageEnvelope $def."""
        return {
            "value": self.value,
            "rowsConsidered": self.rowsConsidered,
            "rowsAvailable": self.rowsAvailable,
            "truncated": self.truncated,
            "sequenceRange": [self.sequenceRange[0], self.sequenceRange[1]],
            "coverage": self.coverage,
            "label": self.label,
        }

    @classmethod
    def empty(cls, value: Any = None) -> "CoverageEnvelope":
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
        )


def envelope_for(
    value: Any,
    primary_rows: Sequence[Mapping[str, Any]],
    primary_available: int,
    aux_scans: Sequence[tuple[Sequence[Mapping[str, Any]], int]] = (),
) -> CoverageEnvelope:
    """The envelope for a figure computed over ``primary_rows`` when the
    ledger holds ``primary_available`` rows in the figure's scope.

    ``aux_scans`` are ``(rows, available)`` pairs for the metric's
    auxiliary lookups (e.g. the rejection entries a rate resolves links
    through): a short auxiliary scan also marks the figure truncated —
    the primary population was complete but the linkage that qualifies
    it was not (the G-01 shape).

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
    if primary_available <= 0:
        return CoverageEnvelope.empty(value)
    return CoverageEnvelope(
        value=value,
        rowsConsidered=considered,
        rowsAvailable=primary_available,
        truncated=truncated,
        sequenceRange=sequence_range,
        coverage=round(considered / primary_available, 6),
        label=_LABEL_PARTIAL if truncated else _LABEL_COMPLETE,
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
