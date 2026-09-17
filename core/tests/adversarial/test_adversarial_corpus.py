"""Adversarial corpus test driver — FR-M46-09/10, SEC-34 (N2-T33).

Runs every fixture in every registered batch. Hosted-execution and
passive-observation surfaces run as SEPARATE tests (FR-M46-10): a control
that blocks hosted work but blind observation (or vice versa) is exactly
the asymmetry the requirement names.

Batch progress toward the ≥100-fixture floor is asserted at batch level,
not padded: the count is reported and the floor enforced once the corpus
declares itself complete (batches register in `BATCHES` as they land).
"""

from __future__ import annotations

import pytest

from . import corpus_batch1, corpus_batch2, corpus_batch3
from .harness import (
    Fixture,
    SURFACE_HOSTED,
    SURFACE_PASSIVE,
    run_fixture,
)

BATCHES = [corpus_batch1.fixtures, corpus_batch2.fixtures, corpus_batch3.fixtures]


def _all_fixtures() -> list[Fixture]:
    fixtures: list[Fixture] = []
    for batch in BATCHES:
        fixtures.extend(batch())
    return fixtures


def _ids(surface: str) -> list[str]:
    return [f.id for f in _all_fixtures() if f.surface == surface]


def _run(surface: str, fixture_id: str, tmp_path) -> None:
    fixture = next(f for f in _all_fixtures() if f.id == fixture_id)
    report = run_fixture(fixture, tmp_path)
    # The harness re-checks the surface split: a fixture can never be
    # counted on the wrong side of the hosted/passive line.
    assert report.surface == surface


@pytest.mark.parametrize("fixture_id", _ids(SURFACE_HOSTED))
def test_hosted_execution(fixture_id: str, tmp_path) -> None:
    """Every block on the execution path leaves a usable evidence record —
    asserted inside each fixture (trigger ABORT, named refusal, redaction
    marker, or chain entry), not here."""
    _run(SURFACE_HOSTED, fixture_id, tmp_path)


@pytest.mark.parametrize("fixture_id", _ids(SURFACE_PASSIVE))
def test_passive_observation(fixture_id: str, tmp_path) -> None:
    """Every detection on the observation path is a readable verdict."""
    _run(SURFACE_PASSIVE, fixture_id, tmp_path)


def test_corpus_invariants() -> None:
    fixtures = _all_fixtures()
    ids = [f.id for f in fixtures]
    assert len(ids) == len(set(ids)), "duplicate fixture ids"
    surfaces = {f.surface for f in fixtures}
    assert surfaces == {SURFACE_HOSTED, SURFACE_PASSIVE}
    # FR-M46-09: no known critical escape means every hosted block produced
    # its evidence record (asserted per fixture). The floor is enforced:
    # below 100 the corpus is a partial batch and says so here.
    assert len(fixtures) >= 100, (
        f"corpus has {len(fixtures)} fixtures; the FR-M46-09 floor is 100"
    )
