"""Versioned measurement definitions (FR-M41-13; N1 Workstream C task 13).

The definitions record is one versioned value covering the seven FR-M41-13
dimensions; every figure records WHICH version produced it — in the
result (``measurementDefinitions``) and on the coverage envelope — so a
figure stays attributable to the definition of its statistic after the
definition changes.
"""

from __future__ import annotations

from pathlib import Path

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics.compare import compute_agent_comparison
from meridian_core.metrics.coverage import envelope_for
from meridian_core.metrics.definitions import (
    MEASUREMENT_DEFINITIONS_VERSION,
    MeasurementDefinitions,
    current_definitions,
)
from meridian_core.metrics.reasons import compute_reason_distribution
from meridian_core.metrics.trust import compute_rejection_rate
from meridian_core.rejection.taxonomy import load_taxonomy


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def _diff_entry(story: str, actor: str):
    return {
        "story_id": story,
        "phase": "build",
        "loop_id": "L",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }


class TestMeasurementDefinitionsRecord:
    def test_record_covers_all_seven_fr_m41_13_dimensions(self):
        record = current_definitions()
        payload = record.to_dict()
        for key in (
            "proposedChangeUnit",
            "rejectionTaxonomyVersion",
            "observationWindow",
            "lateRejectionTreatment",
            "censoring",
            "costAllocation",
            "greenfieldBoundary",
        ):
            assert key in payload, f"missing dimension {key}"
            assert isinstance(payload[key], str) and payload[key].strip()
        assert payload["version"] == MEASUREMENT_DEFINITIONS_VERSION

    def test_record_is_frozen_and_versioned(self):
        record = current_definitions()
        assert isinstance(record, MeasurementDefinitions)
        try:
            record.version = "999"  # type: ignore[misc]
        except AttributeError:
            pass
        else:  # pragma: no cover - dataclass frozen must refuse
            raise AssertionError("MeasurementDefinitions must be frozen")

    def test_taxonomy_version_is_embedded_from_the_loaded_taxonomy(self):
        # D25 pattern: the taxonomy versions itself; the definitions
        # record embeds whatever version is live, so a workspace taxonomy
        # bump is reflected in the record automatically.
        record = current_definitions()
        assert record.rejection_taxonomy_version == str(load_taxonomy().version)
        assert record.rejection_taxonomy_version.isdigit()

    def test_definitions_and_taxonomy_versions_are_distinct_tracks(self):
        # The definitions version versions the MEANING of the seven
        # dimensions; the taxonomy version versions the reason classes.
        # Both are recorded; the taxonomy track is read live from the
        # loaded taxonomy (a workspace bump shows up without a code
        # change), the definitions track is a code constant.
        record = current_definitions()
        assert record.version == MEASUREMENT_DEFINITIONS_VERSION
        assert record.rejection_taxonomy_version == str(load_taxonomy().version)


class TestDefinitionsRecordedOnEveryFigure:
    def test_rejection_rate_records_definitions_on_result_and_envelope(
        self, tmp_path: Path
    ):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            result = compute_rejection_rate(ledger)
        finally:
            ledger.close()
        record = result["measurementDefinitions"]
        assert record["version"] == MEASUREMENT_DEFINITIONS_VERSION
        assert (
            record["rejectionTaxonomyVersion"]
            == str(load_taxonomy().version)
        )
        # The envelope carries the VERSION that produced the figure —
        # the same-operation (NFR-34) attribution FR-M41-13 demands.
        assert result["coverage"]["measurementDefinitions"] == record["version"]

    def test_agent_comparison_records_definitions(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            ledger.append(_diff_entry("s1", "agent-b"))
            result = compute_agent_comparison(ledger, story_id="s1")
        finally:
            ledger.close()
        assert (
            result["measurementDefinitions"]["version"]
            == MEASUREMENT_DEFINITIONS_VERSION
        )
        assert (
            result["coverage"]["measurementDefinitions"]
            == MEASUREMENT_DEFINITIONS_VERSION
        )

    def test_reason_distribution_records_definitions(self, tmp_path: Path):
        ledger = _ledger(tmp_path)
        try:
            ledger.append(
                {
                    **_diff_entry("s1", "reviewer"),
                    "action_type": "rejection",
                    "phase": "review",
                    "decision": "rejected",
                    "rework_reason": "missing-tests",
                }
            )
            result = compute_reason_distribution(ledger)
        finally:
            ledger.close()
        assert (
            result["measurementDefinitions"]["version"]
            == MEASUREMENT_DEFINITIONS_VERSION
        )
        assert (
            result["coverage"]["measurementDefinitions"]
            == MEASUREMENT_DEFINITIONS_VERSION
        )

    def test_envelope_carries_no_version_when_unset(self, tmp_path: Path):
        # Older surfaces stay valid: an envelope built without definitions
        # omits the key rather than fabricating one.
        ledger = _ledger(tmp_path)
        try:
            ledger.append(_diff_entry("s1", "agent-a"))
            rows = ledger.query()
            envelope = envelope_for(1.0, rows, len(rows))
        finally:
            ledger.close()
        assert "measurementDefinitions" not in envelope.to_dict()
