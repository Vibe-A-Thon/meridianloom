"""Policy engine (FR-M12-01, FR-M12-08) with machine-checkable DoR/DoD
criteria (FR-M12-09; F1 Workstream B task 9).

Policy packs are declarative YAML (policy/governance.yaml in the repository,
overridable per workspace at .meridian/policy/governance.yaml — first readable
file wins). Parsing is fail-closed like the FR-M34-04 allow-list: any schema
error yields a pack whose errors are listed and whose every evaluation
blocks — a malformed policy NEVER opens a gate.

The engine evaluates a packet/PR payload against a named gate profile and
returns per-criterion pass/fail plus an overall verdict with reasons. The
F1-A4 ACP permission allow-list is one section (acpPermissions) of the
general pack (FR-M12-08); the extension host keeps consuming the dedicated
acp-permissions.yaml unchanged.

Criterion truth table coverage: requiredFields, testEvidence,
securityScan, humanApproval; unknown profile; fail-closed packs; profile
selection; verdict shape; first-readable-file-wins; ledger recording of
every gate decision BEFORE the RPC returns (FR-M10-08); G5 (governor
disabled -> TIER_DISABLED, recorder untouched).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import engine, policy
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer


# -- fixtures ----------------------------------------------------------------

VALID_PACK = """
version: 2

codingStandards:
  - docs/standards/python.md
egressAllowlist:
  - pypi.org
permittedTools:
  - git
  - pytest
budgetCeilings:
  usdPerStory: 25
tierThresholds:
  firstPassYield: 0.85

acpPermissions:
  adapters:
    '*':
      probation: [read, search]
      active: [read, search, edit, execute]

protectedBranches: [main]

profiles:
  ready:
    description: Definition of Ready
    criteria:
      - id: ready-fields
        kind: requiredFields
        fields: [storyId, branch, headCommit]
  verify:
    description: Build verification
    criteria:
      - id: ready-fields
        kind: requiredFields
        fields: [storyId, branch, headCommit]
      - id: tests-pass
        kind: testEvidence
  security:
    description: Security gate
    criteria:
      - id: scan-clean
        kind: securityScan
      - id: ready-fields
        kind: requiredFields
        fields: [branch]
  review:
    description: Definition of Done
    criteria:
      - id: tests-pass
        kind: testEvidence
      - id: scan-clean
        kind: securityScan
      - id: lead-approval
        kind: humanApproval
        roles: [lead, maintainer]
"""

GOOD_PACKET = {
    "storyId": "story-42",
    "branch": "feature/story-42",
    "headCommit": "abc123",
    "evidence": [
        {"kind": "test", "status": "passed", "ref": "pytest"},
        {"kind": "security-scan", "status": "passed", "criticalFindings": 0},
    ],
    "approvals": [
        {"approver": {"name": "Ada", "email": "ada@example.com"}, "role": "lead"}
    ],
}


@pytest.fixture()
def pack() -> policy.PolicyPack:
    parsed = policy.parse_policy_pack(VALID_PACK, "test-pack")
    assert parsed.errors == []
    return parsed


def make_server(tmp_path: Path, pack_text: str = VALID_PACK) -> SidecarServer:
    """A server with an injected ledger and a workspace whose policy file
    exists (so the governor RPCs find the pack without explicit policyPath)."""
    workspace = tmp_path / "workspace"
    (workspace / ".meridian" / "policy").mkdir(parents=True)
    (workspace / ".meridian" / "policy" / "governance.yaml").write_text(
        pack_text, encoding="utf-8"
    )
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger)
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "workspaceDir": str(workspace),
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    return server


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


# -- parsing (fail-closed) ----------------------------------------------------


class TestPackParsing:
    def test_valid_pack_exposes_fr_m12_08_sections(self, pack: policy.PolicyPack):
        assert pack.version == 2
        assert pack.coding_standards == ["docs/standards/python.md"]
        assert pack.egress_allowlist == ["pypi.org"]
        assert pack.permitted_tools == ["git", "pytest"]
        assert pack.budget_ceilings == {"usdPerStory": 25}
        assert pack.tier_thresholds == {"firstPassYield": 0.85}
        # The F1-A4 allow-list as a section of the general pack.
        assert pack.acp_permissions["adapters"]["*"]["active"] == [
            "read",
            "search",
            "edit",
            "execute",
        ]

    def test_profiles_and_protected_branches(self, pack: policy.PolicyPack):
        assert set(pack.profiles) == {"ready", "verify", "security", "review"}
        assert pack.protected_branches == ["main"]
        review = pack.profiles["review"]
        assert [c.id for c in review.criteria] == [
            "tests-pass",
            "scan-clean",
            "lead-approval",
        ]
        assert review.criteria[2].roles == ("lead", "maintainer")

    def test_malformed_yaml_is_fail_closed(self):
        parsed = policy.parse_policy_pack("version: [unclosed", "broken")
        assert parsed.fail_closed
        assert parsed.errors
        verdict = engine.evaluate(GOOD_PACKET, "verify", parsed)
        assert verdict.passed is False
        assert any("YAML" in reason for reason in verdict.reasons)

    def test_missing_version_is_fail_closed(self):
        parsed = policy.parse_policy_pack("profiles: {}\n", "noversion")
        assert parsed.fail_closed
        assert any("version" in error for error in parsed.errors)

    def test_unknown_criterion_kind_is_fail_closed(self):
        parsed = policy.parse_policy_pack(
            "version: 2\nprofiles:\n  p:\n    criteria:\n"
            "      - id: x\n        kind: crystalBall\n",
            "badkind",
        )
        assert parsed.fail_closed
        assert any("crystalBall" in error for error in parsed.errors)

    def test_unknown_top_level_keys_are_rejected(self):
        parsed = policy.parse_policy_pack(
            "version: 2\nsurprise: true\nprofiles: {}\n", "badkey"
        )
        assert parsed.fail_closed
        assert any("surprise" in error for error in parsed.errors)

    def test_protected_branches_must_be_strings(self):
        parsed = policy.parse_policy_pack(
            "version: 2\nprotectedBranches: [main, 7]\nprofiles: {}\n", "badbranch"
        )
        assert parsed.fail_closed

    def test_missing_file_is_fail_closed(self, tmp_path: Path):
        parsed = policy.load_policy_pack([tmp_path / "nope.yaml"])
        assert parsed.fail_closed
        assert any("no policy file" in error for error in parsed.errors)

    def test_first_readable_file_wins(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        (workspace / ".meridian" / "policy").mkdir(parents=True)
        (workspace / ".meridian" / "policy" / "governance.yaml").write_text(
            "version: 2\nprofiles:\n  only-local:\n    criteria: []\n",
            encoding="utf-8",
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "governance.yaml").write_text(VALID_PACK, encoding="utf-8")
        loaded = policy.load_policy_pack(
            [workspace / ".meridian" / "policy" / "governance.yaml", repo / "governance.yaml"]
        )
        assert set(loaded.profiles) == {"only-local"}


# -- criterion truth table ----------------------------------------------------


class TestRequiredFields:
    def test_all_present_passes(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "ready", pack)
        by_id = {c.id: c for c in verdict.criteria}
        assert by_id["ready-fields"].passed is True

    @pytest.mark.parametrize("missing", ["storyId", "branch", "headCommit"])
    def test_each_missing_field_fails_with_reason(self, pack, missing):
        packet = {key: value for key, value in GOOD_PACKET.items() if key != missing}
        verdict = engine.evaluate(packet, "ready", pack)
        criterion = {c.id: c for c in verdict.criteria}["ready-fields"]
        assert criterion.passed is False
        assert missing in criterion.reason
        assert verdict.passed is False

    def test_blank_string_counts_as_missing(self, pack):
        packet = {**GOOD_PACKET, "branch": "   "}
        verdict = engine.evaluate(packet, "ready", pack)
        assert verdict.passed is False


class TestTestEvidence:
    def test_passing_test_artifact_passes(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "verify", pack)
        assert {c.id: c for c in verdict.criteria}["tests-pass"].passed is True

    def test_failing_test_run_fails(self, pack):
        packet = {
            **GOOD_PACKET,
            "evidence": [{"kind": "test", "status": "failed"}],
        }
        verdict = engine.evaluate(packet, "verify", pack)
        criterion = {c.id: c for c in verdict.criteria}["tests-pass"]
        assert criterion.passed is False
        assert "failed" in criterion.reason

    def test_no_test_evidence_fails(self, pack):
        packet = {**GOOD_PACKET, "evidence": [{"kind": "security-scan", "status": "passed"}]}
        verdict = engine.evaluate(packet, "verify", pack)
        assert {c.id: c for c in verdict.criteria}["tests-pass"].passed is False


class TestSecurityScan:
    def test_clean_scan_passes(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "security", pack)
        assert {c.id: c for c in verdict.criteria}["scan-clean"].passed is True

    @pytest.mark.parametrize(
        "artifact",
        [
            {"kind": "security-scan", "status": "failed"},
            {"kind": "security-scan", "status": "passed", "criticalFindings": 3},
        ],
    )
    def test_dirty_scan_fails(self, pack, artifact):
        verdict = engine.evaluate(
            {**GOOD_PACKET, "evidence": [artifact]}, "security", pack
        )
        assert {c.id: c for c in verdict.criteria}["scan-clean"].passed is False

    def test_max_critical_findings_threshold(self):
        parsed = policy.parse_policy_pack(
            "version: 2\nprofiles:\n  p:\n    criteria:\n"
            "      - id: scan\n        kind: securityScan\n        maxCriticalFindings: 2\n",
            "t",
        )
        packet = {
            "evidence": [{"kind": "security-scan", "status": "passed", "criticalFindings": 2}]
        }
        assert engine.evaluate(packet, "p", parsed).passed is True
        packet["evidence"][0]["criticalFindings"] = 3
        assert engine.evaluate(packet, "p", parsed).passed is False


class TestHumanApproval:
    def test_approval_with_allowed_role_passes(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "review", pack)
        assert {c.id: c for c in verdict.criteria}["lead-approval"].passed is True

    def test_wrong_role_fails(self, pack):
        packet = {
            **GOOD_PACKET,
            "approvals": [
                {"approver": {"name": "Ada", "email": "ada@example.com"}, "role": "intern"}
            ],
        }
        verdict = engine.evaluate(packet, "review", pack)
        criterion = {c.id: c for c in verdict.criteria}["lead-approval"]
        assert criterion.passed is False
        assert "intern" in criterion.reason

    def test_anonymous_approval_is_impossible(self, pack):
        # FR-M12-07: anonymous approval SHALL NOT be possible — an approval
        # without a named human fails the criterion.
        packet = {**GOOD_PACKET, "approvals": [{"role": "lead"}]}
        verdict = engine.evaluate(packet, "review", pack)
        assert {c.id: c for c in verdict.criteria}["lead-approval"].passed is False

    def test_no_approvals_fails(self, pack):
        verdict = engine.evaluate({**GOOD_PACKET, "approvals": []}, "review", pack)
        assert {c.id: c for c in verdict.criteria}["lead-approval"].passed is False


# -- verdict shape ------------------------------------------------------------


class TestVerdict:
    def test_full_packet_passes_review(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "review", pack)
        assert verdict.passed is True
        assert verdict.profile == "review"
        assert list(verdict.reasons) == []
        assert all(c.passed for c in verdict.criteria)
        assert len(verdict.criteria) == 3

    def test_failing_criteria_land_in_reasons(self, pack):
        verdict = engine.evaluate({"storyId": "s"}, "review", pack)
        assert verdict.passed is False
        assert len(verdict.reasons) == len(
            [c for c in verdict.criteria if not c.passed]
        )

    def test_unknown_profile_blocks(self, pack):
        verdict = engine.evaluate(GOOD_PACKET, "nope", pack)
        assert verdict.passed is False
        assert any("nope" in reason for reason in verdict.reasons)

    def test_fail_closed_pack_blocks_everything(self, pack):
        broken = policy.fail_closed_pack("t", ["broken for the test"])
        verdict = engine.evaluate(GOOD_PACKET, "review", broken)
        assert verdict.passed is False
        assert verdict.fail_closed is True
        assert list(verdict.reasons) == ["broken for the test"]

    def test_profile_with_no_criteria_passes(self):
        parsed = policy.parse_policy_pack(
            "version: 2\nprofiles:\n  open:\n    criteria: []\n", "t"
        )
        assert engine.evaluate({}, "open", parsed).passed is True


# -- RPC: gate.evaluate, gate.profiles ----------------------------------------


class TestGateEvaluateRpc:
    def test_evaluate_returns_verdict_shape(self, tmp_path):
        server = make_server(tmp_path)
        response = call(
            server,
            "gate.evaluate",
            {"storyId": "s1", "gate": "verify", "packet": GOOD_PACKET},
        )
        result = response["result"]
        assert result["decision"] == "pass"
        assert result["profile"] == "verify"
        assert result["policyVersion"] == "governance/v2"
        assert result["failClosed"] is False
        assert {c["id"]: c["passed"] for c in result["criteria"]} == {
            "ready-fields": True,
            "tests-pass": True,
        }

    def test_decision_is_recorded_in_ledger_before_returning(self, tmp_path):
        server = make_server(tmp_path)
        response = call(
            server,
            "gate.evaluate",
            {"storyId": "s1", "gate": "verify", "packet": {"storyId": "s1"}},
        )
        assert response["result"]["decision"] == "block"
        ledger = server.ledger
        assert ledger is not None
        rows = ledger.query(action_type="gate")
        assert len(rows) == 1
        row = rows[0]
        assert row["decision"] == "rejected"
        assert row["story_id"] == "s1"
        assert row["policy_version"] == "governance/v2"
        assert row["rework_reason"]
        detail = json.loads(
            ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["gate"] == "verify"
        assert detail["criteria"][0]["passed"] is False

    def test_fail_closed_pack_blocks_and_records(self, tmp_path):
        server = make_server(tmp_path, pack_text="version: [broken")
        response = call(
            server, "gate.evaluate", {"storyId": "s1", "gate": "verify", "packet": {}}
        )
        result = response["result"]
        assert result["decision"] == "block"
        assert result["failClosed"] is True
        assert result["reasons"]
        assert len(server.ledger.query(action_type="gate")) == 1

    def test_missing_packet_is_invalid_params(self, tmp_path):
        server = make_server(tmp_path)
        response = call(server, "gate.evaluate", {"storyId": "s1", "gate": "verify"})
        assert response["error"]["code"] == protocol.INVALID_PARAMS

    def test_governor_disabled_refuses_everything_and_touches_nothing(self, tmp_path):
        # G5: with the governor tier off, gate RPCs are TIER_DISABLED and the
        # recorder (ledger) is untouched — no directory is even created.
        workspace = tmp_path / "workspace"
        (workspace / ".meridian" / "policy").mkdir(parents=True)
        (workspace / ".meridian" / "policy" / "governance.yaml").write_text(
            VALID_PACK, encoding="utf-8"
        )
        server = SidecarServer()  # default tiers: flight-recorder only
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "workspaceDir": str(workspace),
                },
            }
        )
        for method, params in (
            ("gate.evaluate", {"storyId": "s", "gate": "verify", "packet": {}}),
            ("gate.profiles", {}),
        ):
            response = call(server, method, params)
            assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED, method
        assert not (workspace / ".meridian" / "ledger").exists()


class TestGateProfilesRpc:
    def test_profiles_lists_every_profile_with_criteria(self, tmp_path):
        server = make_server(tmp_path)
        result = call(server, "gate.profiles", {})["result"]
        assert result["policyVersion"] == "governance/v2"
        by_name = {p["name"]: p for p in result["profiles"]}
        assert set(by_name) == {"ready", "verify", "security", "review"}
        assert by_name["review"]["criteria"] == ["tests-pass", "scan-clean", "lead-approval"]
        assert by_name["ready"]["description"] == "Definition of Ready"

    def test_profiles_on_fail_closed_pack_reports_errors(self, tmp_path):
        server = make_server(tmp_path, pack_text="version: [broken")
        result = call(server, "gate.profiles", {})["result"]
        assert result["failClosed"] is True
        assert result["profiles"] == []
        assert result["errors"]
