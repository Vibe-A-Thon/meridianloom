"""External PR gating + PR ingest as a story (FR-M35-04, FR-M35-05; F1
Workstream B task 12).

A PR payload in the recorded-real gh-api shape (the fixture extends the
Copilot observer's pulls.json PR 41 with the commit and file arrays the
live API carries) is ingested as a Meridian story:

* the PR is the story's ledger origin record (actionType pr_ingest,
  origin connector, run linkage) — written before the RPC returns
  (FR-M10-08);
* every hunk is attributed to its agent — Co-Authored-By trailer evidence
  wins, author markers next, the heuristic fallback always labelled
  inferred (FR-M35-02, G3);
* the packet is routed through the Verify/Security/Review gate profiles
  and each verdict is recorded (FR-M35-04);
* merge is permitted only via the merge gate: pr/status consults
  check_merge, which requires a recorded human approval bound to the head
  commit when the PR targets a protected branch (FR-M12-05);
* AC-32 reconciliation: the external agent's pass, the gates and the
  approver land in ONE contiguous ledger range over the story;
* G5: governor disabled -> TIER_DISABLED, the recorder tier is untouched.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance.identity import HumanIdentity, StaticIdentityProvider
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.pr import ingest as pr_ingest
from meridian_core.server import SidecarServer

FIXTURE = Path(__file__).parent / "fixtures" / "gh_api" / "pull_41_detail.json"

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles:
  verify:
    criteria:
      - id: ready-fields
        kind: requiredFields
        fields: [storyId, branch, headCommit]
      - id: tests-pass
        kind: testEvidence
  security:
    criteria:
      - id: ready-fields
        kind: requiredFields
        fields: [storyId, branch, headCommit]
      - id: scan-clean
        kind: securityScan
  review:
    criteria:
      - id: ready-fields
        kind: requiredFields
        fields: [storyId, branch, headCommit]
      - id: tests-pass
        kind: testEvidence
      - id: scan-clean
        kind: securityScan
      - id: lead-approval
        kind: humanApproval
        roles: [lead, maintainer]
"""

APPROVER = {"name": "Ada Lovelace", "email": "ada@example.com"}


@pytest.fixture()
def pr_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def pack_path(tmp_path: Path) -> Path:
    target = tmp_path / "governance.yaml"
    target.write_text(PACK_TEXT, encoding="utf-8")
    return target


@pytest.fixture()
def server(tmp_path: Path, pack_path: Path) -> SidecarServer:
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(
        ledger=ledger,
        identity_provider=StaticIdentityProvider(
            HumanIdentity(name=APPROVER["name"], email=APPROVER["email"])
        ),
    )
    response = instance.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    assert "result" in response
    return instance


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def ingest(server: SidecarServer, pack_path: Path, pr: dict, **extra) -> dict:
    params = {"pr": pr, "policyPath": str(pack_path)}
    params.update(extra)
    response = call(server, "pr/ingest", params)
    assert "result" in response, response
    return response["result"]


# -- payload normalisation (the pure ingest module) --------------------------


class TestParsePr:
    def test_fixture_parses(self, pr_payload: dict):
        pr = pr_ingest.parse_pr(pr_payload)
        assert pr.repo == "acme/payments"
        assert pr.number == 41
        assert pr.branch == "copilot/add-retry-logic"
        assert pr.head_commit == pr_payload["head"]["sha"]
        assert pr.base_branch == "main"
        assert pr.author_login == "copilot-swe-agent"

    def test_missing_head_sha_is_refused(self, pr_payload: dict):
        del pr_payload["head"]["sha"]
        with pytest.raises(pr_ingest.IngestError, match="head.sha"):
            pr_ingest.parse_pr(pr_payload)

    def test_missing_repo_is_refused(self, pr_payload: dict):
        del pr_payload["head"]["repo"]
        pr_payload["base"].pop("repo", None)
        with pytest.raises(pr_ingest.IngestError, match="full_name"):
            pr_ingest.parse_pr(pr_payload)

    def test_subject_shape(self):
        assert pr_ingest.subject_for("acme/payments", 41) == "pr:acme/payments#41"

    def test_ticket_from_body(self, pr_payload: dict):
        pr = pr_ingest.parse_pr(pr_payload)
        assert pr_ingest.ticket_for(pr) == "PROJ-1234"


class TestAgentAttribution:
    def test_trailer_evidence_wins(self, pr_payload: dict):
        pr = pr_ingest.parse_pr(pr_payload)
        agents = pr_ingest.resolve_agents(pr)
        assert agents[0].vendor == "github-copilot"
        assert agents[0].source == "trailer"
        assert agents[0].confidence == "telemetry"

    def test_author_marker_without_trailer(self, pr_payload: dict):
        pr_payload["commits"] = []
        pr = pr_ingest.parse_pr(pr_payload)
        agents = pr_ingest.resolve_agents(pr)
        assert agents[0].vendor == "github-copilot"
        assert agents[0].source == "author-marker"

    def test_unknown_author_falls_back_inferred(self, pr_payload: dict):
        pr_payload["commits"] = []
        pr_payload["user"] = {"login": "sindhu", "type": "User"}
        pr = pr_ingest.parse_pr(pr_payload)
        agents = pr_ingest.resolve_agents(pr)
        assert agents[0].vendor == "unknown"
        assert agents[0].confidence == "inferred"
        assert agents[0].source == "heuristic"

    def test_hunks_attributed_to_agent(self, pr_payload: dict):
        pr = pr_ingest.parse_pr(pr_payload)
        hunks = pr_ingest.attribute_hunks(pr)
        assert len(hunks) == 1
        hunk = hunks[0]
        assert hunk.path == "src/payments/client.py"
        assert hunk.agent.vendor == "github-copilot"
        assert hunk.new_count > 0
        assert "trailer" in hunk.rationale

    def test_multi_agent_pr_degrades_confidence(self, pr_payload: dict):
        second = json.loads(json.dumps(pr_payload["commits"][0]))
        second["commit"]["message"] = (
            "Second pass\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        pr_payload["commits"].append(second)
        pr = pr_ingest.parse_pr(pr_payload)
        agents = pr_ingest.resolve_agents(pr)
        assert {a.vendor for a in agents} == {"github-copilot", "claude"}
        hunks = pr_ingest.attribute_hunks(pr)
        assert all(h.agent.confidence == "inferred" for h in hunks)
        assert all("multiple agents" in h.rationale for h in hunks)


# -- the RPC surface ----------------------------------------------------------


class TestPrIngestRpc:
    def test_ingest_records_origin_passes_and_gates(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        result = ingest(server, pack_path, pr_payload)
        assert result["storyId"] == "PROJ-1234"
        assert result["subject"] == "pr:acme/payments#41"
        assert result["headCommit"] == pr_payload["head"]["sha"]
        assert [g["gate"] for g in result["gates"]] == ["verify", "security", "review"]
        # No evidence or approvals in the payload: every content gate blocks.
        assert all(g["decision"] == "block" for g in result["gates"])

        rows = server.ledger.query(story_id="PROJ-1234", limit=1000)
        action_types = [r["action_type"] for r in rows]
        # origin + one agent pass + three gate evaluations, nothing else.
        assert action_types == ["pr_ingest", "diff", "gate", "gate", "gate"]

        origin = rows[0]
        assert origin["origin"] == "connector"
        assert origin["run_id"] == "pr:acme/payments#41"
        assert origin["phase"] == "intake"
        assert origin["decision"] == "proposed"

        passed = rows[1]
        assert passed["actor_id"].startswith("github-copilot:")
        assert passed["vendor"] == "github-copilot"
        assert passed["observation_confidence"] == "telemetry"
        assert passed["decision"] == "proposed"

    def test_entries_written_before_response(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        # FR-M10-08: the returned sequences exist in the ledger at return time.
        result = ingest(server, pack_path, pr_payload)
        ledger = server.ledger
        assert ledger.get_entry(result["sequences"]["origin"]) is not None
        for seq in result["sequences"]["passes"] + result["sequences"]["gates"]:
            assert ledger.get_entry(seq) is not None

    def test_ingest_with_evidence_passes_gates(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        result = ingest(
            server,
            pack_path,
            pr_payload,
            evidence=[
                {"kind": "test", "status": "passed"},
                {"kind": "security-scan", "status": "passed", "criticalFindings": 0},
            ],
            approvals=[{"approver": APPROVER, "role": "lead"}],
        )
        assert all(g["decision"] == "pass" for g in result["gates"])

    def test_invalid_payload_is_refused(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        del pr_payload["base"]
        response = call(server, "pr/ingest", {"pr": pr_payload, "policyPath": str(pack_path)})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert server.ledger.query(action_type="pr_ingest", limit=10) == []

    def test_gates_param_overrides_default_chain(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        result = ingest(server, pack_path, pr_payload, gates=["verify"])
        assert [g["gate"] for g in result["gates"]] == ["verify"]


class TestPrStatusRpc:
    def test_status_blocked_without_approval(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        ingest(server, pack_path, pr_payload)
        response = call(
            server,
            "pr/status",
            {"subject": "pr:acme/payments#41", "policyPath": str(pack_path)},
        )
        result = response["result"]
        assert result["ingested"] is True
        assert result["storyId"] == "PROJ-1234"
        assert result["headCommit"] == pr_payload["head"]["sha"]
        assert len(result["gates"]) == 3
        merge = result["merge"]
        assert merge["status"] == "blocked"
        assert merge["requiredApproval"] is True  # base branch main is protected
        assert any("approval" in item for item in merge["missing"])

    def test_merge_requires_recorded_approval(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        ingest(server, pack_path, pr_payload)
        subject = "pr:acme/payments#41"
        head = pr_payload["head"]["sha"]

        response = call(
            server,
            "gate.approve",
            {
                "subject": subject,
                "commit": head,
                "storyId": "PROJ-1234",
                "role": "lead",
                "policyPath": str(pack_path),
            },
        )
        assert response["result"]["recorded"] is True

        status = call(
            server, "pr/status", {"subject": subject, "policyPath": str(pack_path)}
        )["result"]
        assert status["merge"]["status"] == "approved"
        assert status["merge"]["approvalSequence"] is not None
        assert status["merge"]["approver"] == APPROVER

    def test_changed_head_invalidates_approval(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        ingest(server, pack_path, pr_payload)
        subject = "pr:acme/payments#41"
        call(
            server,
            "gate.approve",
            {
                "subject": subject,
                "commit": pr_payload["head"]["sha"],
                "storyId": "PROJ-1234",
                "policyPath": str(pack_path),
            },
        )
        pr_payload["head"]["sha"] = "f" * 40
        ingest(server, pack_path, pr_payload)  # the PR moved on
        status = call(
            server, "pr/status", {"subject": subject, "policyPath": str(pack_path)}
        )["result"]
        assert status["merge"]["status"] == "blocked"
        assert any("invalidated" in item for item in status["merge"]["missing"])

    def test_unknown_pr_reports_not_ingested(
        self, server: SidecarServer, pack_path: Path
    ):
        status = call(
            server,
            "pr/status",
            {"repo": "acme/payments", "number": 999, "policyPath": str(pack_path)},
        )["result"]
        assert status["ingested"] is False
        assert status["storyId"] is None

    def test_status_is_read_only(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        ingest(server, pack_path, pr_payload)
        before = server.ledger.query(limit=1000)
        call(
            server,
            "pr/status",
            {"subject": "pr:acme/payments#41", "policyPath": str(pack_path)},
        )
        assert server.ledger.query(limit=1000) == before


class TestAc32Reconciliation:
    """AC-32: the external agent's pass, the gates, and the approver in one
    ledger range — queried as one contiguous story slice."""

    def test_one_ledger_range_covers_pass_gates_approver(
        self, server: SidecarServer, pack_path: Path, pr_payload: dict
    ):
        result = ingest(
            server,
            pack_path,
            pr_payload,
            evidence=[
                {"kind": "test", "status": "passed"},
                {"kind": "security-scan", "status": "passed", "criticalFindings": 0},
            ],
            approvals=[{"approver": APPROVER, "role": "maintainer"}],
        )
        approval = call(
            server,
            "gate.approve",
            {
                "subject": result["subject"],
                "commit": result["headCommit"],
                "storyId": result["storyId"],
                "role": "maintainer",
                "policyPath": str(pack_path),
            },
        )["result"]

        ledger = server.ledger
        lo = result["sequences"]["origin"]
        hi = approval["sequence"]
        rows = [
            ledger.get_entry(seq)
            for seq in range(lo, hi + 1)
        ]
        # One contiguous range: nothing else interleaved, nothing missing.
        assert all(row is not None for row in rows)
        action_types = [row["action_type"] for row in rows]
        assert action_types[0] == "pr_ingest"
        assert "diff" in action_types  # the external agent's pass
        assert action_types.count("gate") == 3  # verify, security, review
        assert action_types[-1] == "approval"  # the approver
        # And the range is exactly the story: no foreign rows inside it.
        assert all(row["story_id"] == "PROJ-1234" for row in rows)
        # The merge gate reconciles the same range.
        status = call(
            server,
            "pr/status",
            {"subject": result["subject"], "policyPath": str(pack_path)},
        )["result"]
        assert status["merge"]["status"] == "approved"
        assert lo <= status["merge"]["approvalSequence"] <= hi


class TestTierIsolation:
    """G5: the governor tier gate refuses pr/* when disabled; the recorder
    tier keeps working untouched."""

    def test_pr_methods_refused_when_governor_disabled(
        self, tmp_path: Path, pack_path: Path, pr_payload: dict
    ):
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        server = SidecarServer(ledger=ledger)
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {"protocolVersion": protocol.PROTOCOL_VERSION, "client": "pytest"},
            }
        )
        refused = call(server, "pr/ingest", {"pr": pr_payload})
        assert refused["error"]["code"] == protocol.ERROR_TIER_DISABLED
        refused = call(server, "pr/status", {"subject": "pr:acme/payments#41"})
        assert refused["error"]["code"] == protocol.ERROR_TIER_DISABLED
        # The refusal wrote nothing.
        assert ledger.query(limit=10) == []
        # The recorder tier is fully functional (G5).
        health = call(server, "ping", {})
        assert health["result"]["pong"] is True
