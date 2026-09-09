"""Versioned measurement definitions (FR-M41-13; N1 Workstream C task 13).

FR-M41-13: Meridian SHALL version the definition of the proposed-change
unit, the rejection taxonomy, the observation window, the treatment of
late rejections, censoring rules, cost allocation and the
greenfield/brownfield boundary, and SHALL record which version produced
each reported figure.

What a number *means* is part of the number. When the proposed-change
unit or the late-rejection treatment changes, yesterday's rejection rate
and tomorrow's are different statistics — comparable only because the
definitions record says which definition produced each figure. This
module is that record: ONE :class:`MeasurementDefinitions` value per
definitions version, stamped onto every figure's result (under
``measurementDefinitions``) and onto its coverage envelope (the version
string), so the disclosure rides the same operation as the figure
(NFR-34) — never a separate lookup.

The record is code, versioned with the code (like the D25 rejection
taxonomy in ``rejection/taxonomy.py``, whose own version this record
embeds): bump :data:`MEASUREMENT_DEFINITIONS_VERSION` whenever any
dimension's meaning changes. The dimension values below state the rules
the metrics modules actually implement — they are documentation the
figures carry, not aspirations.

Zero model calls (FR-M36-07): a frozen record assembled from the loaded
taxonomy version and constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..rejection.taxonomy import load_taxonomy

__all__ = [
    "MEASUREMENT_DEFINITIONS_VERSION",
    "MeasurementDefinitions",
    "current_definitions",
]

#: Bump when any dimension's MEANING changes (not when its value changes —
#: the taxonomy version field tracks the taxonomy independently).
MEASUREMENT_DEFINITIONS_VERSION = "1"


@dataclass(frozen=True)
class MeasurementDefinitions:
    """The seven FR-M41-13 dimensions, one record per version."""

    version: str
    # The unit the proposed/rejected counts count: a ledger entry with
    # action_type "diff" (the FR-M37-01 unit — trust.py, compare.py).
    proposed_change_unit: str
    # The rejection taxonomy that classified every rejection reason on the
    # figures (embedded, versioned independently — D25 patterns).
    rejection_taxonomy_version: str
    # What bounds the population a figure reports over.
    observation_window: str
    # Whether a rejection recorded outside the window still counts.
    late_rejection_treatment: str
    # What happens to rows the ledger cannot fully characterise.
    censoring: str
    # How spend is attributed to an actor for cost figures.
    cost_allocation: str
    # Where greenfield ends and brownfield begins.
    greenfield_boundary: str

    def to_dict(self) -> dict[str, Any]:
        """The wire/JSON shape — camelCase, like the envelope."""
        return {
            "version": self.version,
            "proposedChangeUnit": self.proposed_change_unit,
            "rejectionTaxonomyVersion": self.rejection_taxonomy_version,
            "observationWindow": self.observation_window,
            "lateRejectionTreatment": self.late_rejection_treatment,
            "censoring": self.censoring,
            "costAllocation": self.cost_allocation,
            "greenfieldBoundary": self.greenfield_boundary,
        }


def current_definitions() -> MeasurementDefinitions:
    """The definitions record that produces figures NOW — the taxonomy
    version is read from the loaded (workspace or shipped) taxonomy, so a
    workspace taxonomy bump is reflected in the record automatically."""
    taxonomy = load_taxonomy()
    return MeasurementDefinitions(
        version=MEASUREMENT_DEFINITIONS_VERSION,
        proposed_change_unit=(
            'a ledger entry with action_type "diff" (the FR-M37-01 unit)'
        ),
        rejection_taxonomy_version=str(taxonomy.version),
        observation_window=(
            "the caller-declared fromSequence/toSequence window, or the full "
            "history from genesis when undeclared (FR-M41-07 cursor scan)"
        ),
        late_rejection_treatment=(
            "a rejection entry counts only when recorded inside the declared "
            "window — the window bounds the rejection capture scan, so a "
            "rejection landing after the window does not mark an in-window "
            "source rejected (trust.py, compare.py)"
        ),
        censoring=(
            "rows without positive authorship evidence read unattributed, "
            "never imputed (FR-M41-04); figures below the attribution floor "
            "read insufficient_coverage (FR-M41-06); empty samples read "
            "insufficient_evidence, never zero (FR-M41-14)"
        ),
        cost_allocation=(
            "cost_usd / tokens_in / tokens_out summed over every in-scope "
            "entry attributed to the actor; when no in-scope entry carries "
            "spend the component reads insufficient_evidence (compare.py)"
        ),
        greenfield_boundary=(
            "the caller-supplied classifier over story commits "
            "(newFileRatioThreshold / maxMedianAgeDays); stories the "
            "classifier declines read unclassified, never dropped (G6)"
        ),
    )
