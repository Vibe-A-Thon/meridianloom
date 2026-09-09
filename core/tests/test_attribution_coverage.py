"""Attribution coverage on every trust metric with a configurable policy
floor (FR-M41-06, AMD-M37, P25; N1 Workstream B T09).

The envelope carries the attribution-coverage dimension of a metric's
population (three-state counts per FR-M41-04); the floor lives in the
governance pack (``attributionCoverageFloor``, workspace-overridable per
the D43 conventions) and below it the metric reads
``insufficient_coverage`` and shows NO value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian_core.governance import policy as governance_policy
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.metrics import coverage as coverage_mod
from meridian_core.metrics import dora as dora_mod
from meridian_core.metrics import score as score_mod
from meridian_core.metrics import trust as trust_mod
from meridian_core.server import SidecarServer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAttributionCoverageBlock:
    def test_counts_and_ratio(self):
        block = coverage_mod.attribution_coverage(
            ["agent", "agent", "human", "unattributed"]
        )
        assert block.agent == 2
        assert block.human == 1
        assert block.unattributed == 1
        assert block.coverage == 0.75
        assert block.floor is None
        assert block.belowFloor is False

    def test_empty_population_covers_completely(self):
        # The empty-sample verdict is the metric's own insufficient_evidence;
        # the attribution dimension has nothing to miss.
        block = coverage_mod.attribution_coverage([], floor=0.9)
        assert block.coverage == 1.0
        assert block.belowFloor is False

    def test_floor_breach(self):
        block = coverage_mod.attribution_coverage(
            ["agent", "unattributed", "unattributed"], floor=0.8
        )
        assert block.coverage == pytest.approx(0.333333)
        assert block.floor == 0.8
        assert block.belowFloor is True

    def test_floor_met_exactly(self):
        block = coverage_mod.attribution_coverage(["agent", "human"], floor=0.5)
        assert block.belowFloor is False

    def test_invalid_floor_is_unconfigured(self):
        for bad in (1.5, -0.1, "high"):
            block = coverage_mod.attribution_coverage(["agent"], floor=bad)
            assert block.floor is None
            assert block.belowFloor is False

    def test_envelope_carries_the_dimension(self):
        rows = [{"seq": 1}, {"seq": 2}]
        envelope = coverage_mod.envelope_for(
            0.5,
            rows,
            2,
            attribution_states=["agent", "unattributed"],
            attribution_floor=0.8,
        )
        payload = envelope.to_dict()
        assert payload["attribution"]["agent"] == 1
        assert payload["attribution"]["unattributed"] == 1
        assert payload["attribution"]["belowFloor"] is True

    def test_envelope_without_attribution_stays_valid(self):
        envelope = coverage_mod.envelope_for(0.5, [{"seq": 1}], 1)
        assert "attribution" not in envelope.to_dict()

    def test_empty_envelope_keeps_attribution(self):
        envelope = coverage_mod.CoverageEnvelope.empty(
            attribution=coverage_mod.attribution_coverage([], floor=0.8)
        )
        assert envelope.to_dict()["attribution"]["coverage"] == 1.0


class TestLedgerRowAttributionState:
    def test_recorded_external_vendor_is_agent(self):
        row = {"vendor": "claude-code", "actor_kind": "external"}
        assert coverage_mod.ledger_row_attribution_state(row) == "agent"

    def test_telemetry_external_session_is_agent(self):
        row = {
            "vendor": "meridian",
            "actor_kind": "external",
            "observation_confidence": "telemetry",
        }
        assert coverage_mod.ledger_row_attribution_state(row) == "agent"

    def test_inferred_external_session_is_agent(self):
        row = {
            "vendor": "meridian",
            "actor_kind": "external",
            "observation_confidence": "inferred",
        }
        assert coverage_mod.ledger_row_attribution_state(row) == "agent"

    def test_meridian_native_actor_is_agent(self):
        for kind in ("orchestrator", "role", "stack", "sub", "xai", "meta"):
            row = {"vendor": "meridian", "actor_kind": kind}
            assert coverage_mod.ledger_row_attribution_state(row) == "agent", kind

    def test_external_direct_has_no_positive_evidence(self):
        row = {
            "vendor": "meridian",
            "actor_kind": "external",
            "observation_confidence": "direct",
        }
        assert coverage_mod.ledger_row_attribution_state(row) == "unattributed"

    def test_missing_fields_are_unattributed(self):
        assert coverage_mod.ledger_row_attribution_state({}) == "unattributed"


def _diff_entry(story: str, actor: str, *, kind: str = "role", vendor=None,
                confidence=None, decision=None):
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": actor,
        "actor_version": "0.0.1",
        "actor_kind": kind,
        "policy_version": "policy-v1",
        "action_type": "diff",
        "repo_id": "edb",
    }
    if vendor is not None:
        entry["vendor"] = vendor
    if confidence is not None:
        entry["observation_confidence"] = confidence
    if decision is not None:
        entry["decision"] = decision
    return entry


@pytest.fixture()
def ledger(tmp_path):
    handle = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    # Three positively-attributable proposed changes and two with no
    # authorship evidence: population coverage = 3/5 < 0.8; agent-one's
    # own coverage = 2/3 (the score population is actor-filtered).
    handle.append(_diff_entry("A", "agent-one"))
    rejected = handle.append(_diff_entry("B", "agent-one"))
    handle.append(
        _diff_entry("C", "agent-one", kind="external", confidence="direct")
    )
    handle.append(
        _diff_entry("D", "ghost", kind="external", confidence="direct")
    )
    handle.append(
        {
            "story_id": "A",
            "phase": "review",
            "loop_id": "rejection",
            "loop_iteration": 0,
            "actor_id": "unknown",
            "actor_version": "0",
            "actor_kind": "external",
            "policy_version": "f0",
            "action_type": "rejection",
            "decision": "rejected",
            "rework_reason": "other",
            "rejected_sequence": rejected.sequence,
            "rejected_commit": "a" * 40,
            "rejecting_commit": "b" * 40,
            "repo_id": "edb",
        }
    )
    yield handle
    handle.close()


class TestRejectionRateFloor:
    def test_below_floor_suppresses_the_value(self, ledger):
        result = trust_mod.compute_rejection_rate(
            ledger, attribution_floor=0.8
        )
        assert result["status"] == "insufficient_coverage"
        assert result["rate"] is None
        assert "below the configured floor" in result["coverageNote"]
        attribution = result["coverage"]["attribution"]
        # Two role-kind diffs are positively attributable; both
        # external/direct diffs carry no authorship evidence.
        assert attribution["agent"] == 2
        assert attribution["unattributed"] == 2
        assert attribution["coverage"] == 0.5
        assert attribution["floor"] == 0.8
        assert attribution["belowFloor"] is True
        # The counts stay visible; only the VALUE is suppressed.
        assert result["proposed"] == 4
        assert result["rejected"] == 1

    def test_at_or_above_floor_reports_the_value(self, ledger):
        result = trust_mod.compute_rejection_rate(
            ledger, attribution_floor=0.5
        )
        assert result["status"] == "ok"
        assert result["rate"] == 0.25
        assert result["coverage"]["attribution"]["belowFloor"] is False
        assert result["coverageNote"] is None

    def test_unconfigured_floor_never_suppresses(self, ledger):
        result = trust_mod.compute_rejection_rate(ledger)
        assert result["status"] == "ok"
        assert result["rate"] == 0.25
        assert result["coverage"]["attribution"]["floor"] is None


class TestTrustScoreFloor:
    def test_below_floor_suppresses_the_score(self, ledger):
        result = score_mod.compute_trust_score(
            ledger, actor_id="agent-one", attribution_floor=0.8
        )
        assert result["status"] == "insufficient_coverage"
        assert result["score"] is None
        assert result["coverageEnvelope"]["attribution"]["belowFloor"] is True

    def test_above_floor_reports_the_score(self, ledger):
        result = score_mod.compute_trust_score(
            ledger, actor_id="agent-one", attribution_floor=0.5
        )
        # "partial": incident linkage is always unknown (FR-M37-03) — the
        # score itself is present once the floor is met.
        assert result["status"] == "partial"
        assert result["score"] is not None


class TestDoraFloor:
    def test_below_floor_suppresses_every_key(self, ledger):
        result = dora_mod.compute_dora_metrics(
            ledger, attribution_floor=0.8
        )
        for key, status in result["status"].items():
            assert status == "insufficient_coverage", key
            assert result["metrics"][key]["value"] is None, key
        attribution = result["coverage"]["attribution"]
        assert attribution["belowFloor"] is True
        # The OTLP export carries the status, never a fabricated value.
        export = dora_mod.export_otlp(result, exported_at="2026-01-01T00:00:00Z")
        for metric in export["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]:
            (point,) = metric["gauge"]["dataPoints"]
            assert "asDouble" not in point
            evidence = {
                attr["key"]: attr["value"]["stringValue"]
                for attr in point["attributes"]
            }
            assert evidence["meridian.evidence"] == "insufficient_coverage"

    def test_above_floor_reports_values(self, ledger):
        result = dora_mod.compute_dora_metrics(ledger, attribution_floor=0.5)
        # No key is suppressed: statuses are the evidence verdicts
        # (unknown keys carry no value by design — never invented).
        assert "insufficient_coverage" not in set(result["status"].values())
        assert result["coverage"]["attribution"]["belowFloor"] is False


class TestPolicyFloorConfig:
    def test_shipped_default_configures_the_floor(self):
        pack = governance_policy.load_policy_pack(
            [REPO_ROOT / "policy" / "governance.yaml"]
        )
        assert pack.fail_closed is False
        assert pack.attribution_coverage_floor == 0.8

    def test_workspace_override_wins(self, tmp_path):
        override = tmp_path / "governance.yaml"
        override.write_text(
            "version: 2\nattributionCoverageFloor: 0.4\n",
            encoding="utf-8",
        )
        pack = governance_policy.load_policy_pack([override])
        assert pack.attribution_coverage_floor == 0.4

    def test_absent_floor_is_unconfigured(self):
        pack = governance_policy.parse_policy_pack("version: 2\n", "inline")
        assert pack.fail_closed is False
        assert pack.attribution_coverage_floor is None

    def test_invalid_floor_fails_closed(self):
        pack = governance_policy.parse_policy_pack(
            "version: 2\nattributionCoverageFloor: 1.5\n", "inline"
        )
        assert pack.fail_closed
        assert any(
            "attributionCoverageFloor" in error for error in pack.errors
        )

    def test_unknown_top_level_section_still_rejected(self):
        pack = governance_policy.parse_policy_pack(
            "version: 2\nattributionFloor: 0.5\n", "inline"
        )
        assert pack.fail_closed


class TestFloorRpc:
    def _server(self, tmp_path, floor):
        pack = tmp_path / f"gov-{floor}.yaml"
        pack.write_text(
            f"version: 2\nattributionCoverageFloor: {floor}\n",
            encoding="utf-8",
        )
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        ledger.append(_diff_entry("A", "agent-one"))
        ledger.append(
            _diff_entry("B", "ghost", kind="external", confidence="direct")
        )
        server = SidecarServer(ledger=ledger)
        return server, ledger, pack

    def test_rpc_below_floor_reads_insufficient_coverage(self, tmp_path):
        server, ledger, pack = self._server(tmp_path, 0.9)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "trust/rejectionRate",
                "params": {"policyPath": str(pack)},
            }
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["status"] == "insufficient_coverage"
        assert result["rate"] is None
        ledger.close()

    def test_rpc_override_floor_reports(self, tmp_path):
        server, ledger, pack = self._server(tmp_path, 0.25)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "trust/rejectionRate",
                "params": {"policyPath": str(pack)},
            }
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["status"] == "ok"
        assert result["rate"] == 0.0
        assert result["coverage"]["attribution"]["coverage"] == 0.5
        ledger.close()
