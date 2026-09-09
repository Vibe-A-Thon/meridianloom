"""Labelled-corpus evaluation of the span classifier (FR-M41-03, AC-42;
N1 Workstream B T11).

The corpus lives at ``tests/fixtures/attribution_corpus.json`` — 206
mixed human/agent/unattributed spans, generated programmatically ONCE by
``tests/fixtures/generate_attribution_corpus.py`` (fixed seed) and
committed, so the published figures are reproducible from the repository
alone. This test recomputes the confusion matrix and the precision,
recall and unknown-coverage figures on every run and asserts the
documented floor: fields labelled ``observed`` achieve at least 95%
precision. The figures are printed so the published numbers are visible
in CI output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core.attribution import spans
from meridian_core.attribution.states import (
    ATTRIBUTION_STATES,
    UNKNOWN_REASONS,
    UNKNOWN_REASON_VOCABULARY_VERSION,
)

CORPUS_PATH = Path(__file__).parent / "fixtures" / "attribution_corpus.json"

#: FR-M41-03's floor: precision of observed claims on the labelled corpus.
OBSERVED_PRECISION_FLOOR = 0.95

STATES = list(ATTRIBUTION_STATES)


@pytest.fixture(scope="module")
def corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert data["size"] >= 200, "FR-M41-03 requires a corpus of >= 200 spans"
    assert data["vocabularyVersion"] == UNKNOWN_REASON_VOCABULARY_VERSION
    return data


@pytest.fixture(scope="module")
def evaluated(corpus):
    """Every span classified once; predictions aligned with ground truth."""
    rows = []
    for span in corpus["spans"]:
        predicted = spans.classify_span(
            author_name=span["authorName"],
            author_email=span["authorEmail"],
            message=span["message"],
            author_time=span["authorTime"],
            installed_at=corpus["installedAt"],
            excluded=span["excluded"],
        )
        rows.append((span, predicted))
    return rows


def _confusion(evaluated):
    matrix = {truth: {pred: 0 for pred in STATES} for truth in STATES}
    for span, predicted in evaluated:
        matrix[span["expectedState"]][predicted.state] += 1
    return matrix


def _precision_recall(matrix):
    figures = {}
    for state in STATES:
        tp = matrix[state][state]
        predicted_as = sum(matrix[truth][state] for truth in STATES)
        actual = sum(matrix[state].values())
        figures[state] = {
            "precision": tp / predicted_as if predicted_as else None,
            "recall": tp / actual if actual else None,
            "support": actual,
        }
    return figures


def _print_report(corpus, matrix, figures, evaluated):
    print()
    print("=" * 64)
    print(
        f"Attribution corpus v{corpus['version']} — {corpus['size']} spans "
        f"(seed {corpus['seed']}, vocabulary v{corpus['vocabularyVersion']})"
    )
    print("=" * 64)
    header = "truth \\ pred   " + "".join(f"{s:<15}" for s in STATES)
    print(header)
    for truth in STATES:
        row = f"{truth:<15}" + "".join(
            f"{matrix[truth][pred]:<15}" for pred in STATES
        )
        print(row)
    print("-" * 64)
    for state in STATES:
        fig = figures[state]
        precision = f"{fig['precision']:.4f}" if fig["precision"] is not None else "n/a"
        recall = f"{fig['recall']:.4f}" if fig["recall"] is not None else "n/a"
        print(
            f"{state:<15} precision={precision}  recall={recall}"
            f"  support={fig['support']}"
        )
    # Observed-claim precision: of the spans the classifier labels
    # observed, the fraction whose ground truth is observed.
    predicted_observed = [
        (span, predicted)
        for span, predicted in evaluated
        if predicted.confidence == "observed"
    ]
    true_observed = sum(
        1 for span, _ in predicted_observed if span["expectedConfidence"] == "observed"
    )
    precision_observed = (
        true_observed / len(predicted_observed) if predicted_observed else None
    )
    # Unknown coverage: the share of the corpus the classifier honestly
    # leaves unattributed, and every such span's recorded reason.
    unattributed = [
        predicted for _, predicted in evaluated if predicted.state == "unattributed"
    ]
    with_reason = sum(1 for p in unattributed if p.unknown_reason in UNKNOWN_REASONS)
    print("-" * 64)
    print(
        f"observed-claim precision: {precision_observed:.4f} "
        f"({true_observed}/{len(predicted_observed)}) "
        f"[floor {OBSERVED_PRECISION_FLOOR}]"
        if precision_observed is not None
        else "observed-claim precision: n/a (no observed claims)"
    )
    print(
        f"unknown coverage: {len(unattributed)}/{len(evaluated)} spans "
        f"unattributed, {with_reason} with a closed-vocabulary reason"
    )
    print("=" * 64)
    return precision_observed, unattributed, with_reason


class TestCorpusContract:
    def test_corpus_size_and_versioning(self, corpus):
        assert corpus["size"] >= 200
        assert corpus["contractVersion"] == "attrib-provenance/v1"

    def test_labels_are_within_the_three_states(self, corpus):
        for span in corpus["spans"]:
            assert span["expectedState"] in STATES
            assert span["expectedConfidence"] in (
                "observed",
                "inferred",
                "unknown",
            )

    def test_every_unattributed_label_names_a_closed_reason(self, evaluated):
        for span, predicted in evaluated:
            if predicted.state == "unattributed":
                assert predicted.unknown_reason in UNKNOWN_REASONS
                assert predicted.reason_version == UNKNOWN_REASON_VOCABULARY_VERSION

    def test_no_field_is_populated_by_invention(self, evaluated):
        # FR-M41-03: fields the evidence cannot support read unknown with
        # a null value — never a fabricated answer.
        for span, predicted in evaluated:
            if span["expectedConfidence"] == "unknown":
                assert predicted.confidence == "unknown"
            if predicted.state in ("agent", "human"):
                assert predicted.unknown_reason is None
            assert predicted.evidence  # the deciding evidence is always named


class TestPublishedFigures:
    def test_confusion_matrix_and_precision_floor(self, corpus, evaluated):
        matrix = _confusion(evaluated)
        figures = _precision_recall(matrix)
        precision_observed, _, _ = _print_report(
            corpus, matrix, figures, evaluated
        )

        # FR-M41-03: observed-labelled fields achieve at least 95%
        # precision on the labelled corpus.
        assert precision_observed is not None
        assert precision_observed >= OBSERVED_PRECISION_FLOOR

        # Per-state precision and recall stay at the documented floor too —
        # the synthetic corpus is contract-labelled, so these are canaries:
        # any classifier change that breaks the contract turns them red.
        for state in ("agent", "human"):
            assert figures[state]["precision"] >= OBSERVED_PRECISION_FLOOR
            assert figures[state]["recall"] >= OBSERVED_PRECISION_FLOOR

    def test_unknown_coverage_is_reported_not_absorbed(self, corpus, evaluated):
        _, unattributed, with_reason = (None, None, None)
        matrix = _confusion(evaluated)
        figures = _precision_recall(matrix)
        _, unattributed, with_reason = _print_report(
            corpus, matrix, figures, evaluated
        )
        # A meaningful share of the corpus honestly reads unattributed...
        assert len(unattributed) >= 30
        # ...and every one of them carries a closed-vocabulary reason.
        assert with_reason == len(unattributed)
