"""Identity assurance (FR-M42-04/05/06, NFR-36, SEC-31, AC-46; N2 Workstream B
tasks T07/T08, decision D38).

D38 (closed): two recorded assurance levels — ``asserted`` (git
user.name/email, locally asserted, spoofable, v1 default) and ``verified``
(OIDC-backed, behind the IdentityProvider stub). This module proves the
load-bearing rules:

T07 / FR-M42-05 — a git name/email never satisfies a policy requiring a
verified approver. The governance pack's ``requiresVerifiedIdentity``
(global boolean, or ``{default, branches}`` for per-branch gates) refuses
an ``asserted`` identity at approval time with the level named, and the
merge gate re-checks the RECORDED level at execution. When the requirement
is unset, ``asserted`` is accepted and recorded as ``asserted`` — never
silently upgraded to ``verified``.

T08 / FR-M42-06 + NFR-36 + SEC-31 + AC-46 — the identity level rides every
approval and permission decision (the approvedBy stamp), the gate
re-validates the binding when the merge is evaluated, and the
ledger-recorded revocation list (``identity.revoke``) binds from the
instant its row commits: new approvals are refused naming ``revokedAt``,
an in-flight merge stops counting the revoked identity's approvals, and an
in-flight merge authorisation is blocked — even one issued before the
revocation timestamp, because revocation is not limited by approval time.
The five-minute bound of NFR-36/AC-46 is the worst-case envelope for OTHER
replicas; in-process propagation is one ledger read (immediate).

Zero model calls (FR-M36-07): identity resolution, policy parsing, ledger
reads — no model anywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import merge_authorisation, merge_gate, policy, revocations
from meridian_core.identity import ResolvedIdentity, StaticIdentityProvider
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

PACK_BASE = """
version: 2
protectedBranches: [main]
profiles: {}
"""

PACK_VERIFIED_GLOBAL = PACK_BASE + "requiresVerifiedIdentity: true\n"

PACK_VERIFIED_PER_BRANCH = (
    PACK_BASE
    + "requiresVerifiedIdentity:\n  default: false\n  branches:\n    main: true\n"
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init")
    git(target, "config", "user.name", "Ada Lovelace")
    git(target, "config", "user.email", "ada@example.com")
    return target


ADA_ASSERTED = ResolvedIdentity(
    id="ada@example.com",
    display_name="Ada Lovelace",
    email="ada@example.com",
    assurance="asserted",
)
ADA_VERIFIED = ResolvedIdentity(
    id="ada@example.com",
    display_name="Ada Lovelace",
    email="ada@example.com",
    assurance="verified",
)
GRACE_VERIFIED = ResolvedIdentity(
    id="grace@example.com",
    display_name="Grace Hopper",
    email="grace@example.com",
    assurance="verified",
)


def make_server(
    tmp_path: Path,
    repo: Path,
    identity: ResolvedIdentity,
    pack_text: str = PACK_BASE,
) -> SidecarServer:
    (repo / ".meridian" / "policy").mkdir(parents=True, exist_ok=True)
    (repo / ".meridian" / "policy" / "governance.yaml").write_text(
        pack_text, encoding="utf-8"
    )
    server = SidecarServer(
        ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()),
        identity_provider=StaticIdentityProvider(identity),
    )
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "client": "pytest",
                "tiers": ["flight-recorder", "governor"],
                "workspaceDir": str(repo),
            },
        }
    )
    return server


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def read_detail(server: SidecarServer, sequence: int) -> dict:
    row = server.ledger.get_entry(sequence)
    return json.loads(
        server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
    )


# -- FR-M42-04: the level is recorded on every decision ---------------------


class TestIdentityLevelRidesDecisions:
    def test_approval_records_verified_level_on_the_stamp(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        response = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" not in response, response
        detail = read_detail(server, response["result"]["sequence"])
        # FR-M42-04/06: the level is bound to the decision, not the session.
        assert detail["approvedBy"]["class"] == "human_individual"
        assert detail["approvedBy"]["identityAssurance"] == "verified"
        assert response["result"]["approvedBy"]["identityAssurance"] == "verified"

    def test_asserted_accepted_and_recorded_as_asserted_when_unset(
        self, tmp_path, repo
    ):
        server = make_server(tmp_path, repo, ADA_ASSERTED, PACK_BASE)
        response = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" not in response, response
        detail = read_detail(server, response["result"]["sequence"])
        # Recorded as asserted — never silently upgraded to verified.
        assert detail["approvedBy"]["identityAssurance"] == "asserted"
        assert detail["approver"]["assurance"] == "asserted"

    def test_permission_decision_records_the_resolved_level(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        response = call(
            server,
            2,
            "acp/permissionDecision",
            {"sessionId": "s1", "outcome": "selected", "optionId": "allow"},
        )
        assert "error" not in response, response
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        assert detail["approvedBy"]["class"] == "human_individual"
        assert detail["approvedBy"]["identityAssurance"] == "verified"

    def test_policy_gate_decision_carries_no_human_assurance(self, tmp_path, repo):
        # FR-M42-08: denied_by_policy is a ruleset_actor decision — the
        # human never saw the prompt, so no human assurance level rides it.
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        call(
            server,
            2,
            "acp/permissionDecision",
            {"sessionId": "s1", "outcome": "denied_by_policy", "reason": "allow-list"},
        )
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        assert detail["approvedBy"]["class"] == "ruleset_actor"
        assert "identityAssurance" not in detail["approvedBy"]


# -- FR-M42-05 (T07): asserted never satisfies a verified-approver policy ---


class TestVerifiedApproverRequired:
    def test_asserted_refused_with_level_named(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_ASSERTED, PACK_VERIFIED_GLOBAL)
        response = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" in response
        message = response["error"]["message"]
        assert "FR-M42-05" in message
        assert "'asserted'" in message  # the level is named
        assert "verified" in message
        assert response["error"]["data"]["code"] == "IDENTITY_ASSURANCE_INSUFFICIENT"
        # FR-M42-05 is a refusal, not a downgrade: nothing is recorded.
        assert server.ledger.query(action_type="approval", limit=10) == []

    def test_verified_identity_satisfies_the_requirement(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_VERIFIED, PACK_VERIFIED_GLOBAL)
        response = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" not in response, response
        assert response["result"]["recorded"] is True

    def test_per_branch_requirement_refuses_only_named_gates(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_ASSERTED, PACK_VERIFIED_PER_BRANCH)
        refused = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" in refused
        assert "FR-M42-05" in refused["error"]["message"]
        accepted = call(
            server,
            3,
            "gate.approve",
            {"subject": "feature/story-1", "commit": "abc123"},
        )
        assert "error" not in accepted, accepted
        detail = read_detail(server, accepted["result"]["sequence"])
        # Accepted on the gate without the requirement — recorded asserted.
        assert detail["approvedBy"]["identityAssurance"] == "asserted"

    def test_merge_gate_revalidates_recorded_level_at_execution(
        self, tmp_path, repo
    ):
        # SEC-31's re-check shape: the approval was recorded legitimately
        # (no requirement at the time); the gate evaluates LATER against
        # the requirement in force NOW and refuses the asserted level.
        server = make_server(tmp_path, repo, ADA_ASSERTED, PACK_BASE)
        approved = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" not in approved, approved
        verified_pack = tmp_path / "verified.yaml"
        verified_pack.write_text(PACK_VERIFIED_GLOBAL, encoding="utf-8")
        status = call(
            server,
            3,
            "gate.status",
            {"subject": "main", "commit": "abc123", "policyPath": str(verified_pack)},
        )
        assert status["result"]["status"] == "blocked"
        assert any(
            "'asserted'" in item and "FR-M42-05" in item
            for item in status["result"]["missing"]
        )
        # And the verified level satisfies the same later evaluation.
        server._identity_provider = StaticIdentityProvider(GRACE_VERIFIED)
        call(server, 4, "gate.approve", {"subject": "main", "commit": "abc123"})
        status = call(
            server,
            5,
            "gate.status",
            {"subject": "main", "commit": "abc123", "policyPath": str(verified_pack)},
        )
        assert status["result"]["status"] == "approved"

    def test_legacy_row_without_recorded_level_never_counts(self, tmp_path, repo):
        # A row from before the level rode the stamp: its assurance is
        # "unrecorded", which is never a silent "verified".
        server = make_server(tmp_path, repo, ADA_ASSERTED, PACK_BASE)
        call(server, 2, "gate.approve", {"subject": "main", "commit": "abc123"})
        row = server.ledger.query(action_type="approval", limit=10)[0]
        detail = read_detail(server, row["seq"])
        del detail["approvedBy"]["identityAssurance"]
        del detail["approver"]
        blob = json.dumps(detail, ensure_ascii=False).encode("utf-8")
        server.ledger.append(
            {
                "story_id": row["story_id"],
                "phase": row["phase"],
                "loop_id": row["loop_id"],
                "loop_iteration": 1,
                "actor_id": row["actor_id"],
                "actor_version": row["actor_version"],
                "actor_kind": row["actor_kind"],
                "policy_version": row["policy_version"],
                "action_type": "approval",
                "decision": "approved",
                "human_actor": row["human_actor"],
                "human_role": row["human_role"],
                "vendor": row["vendor"],
                "observation_confidence": row["observation_confidence"],
                "input": blob,
            }
        )
        verified_pack = tmp_path / "verified.yaml"
        verified_pack.write_text(PACK_VERIFIED_GLOBAL, encoding="utf-8")
        status = call(
            server,
            3,
            "gate.status",
            {
                "subject": "main",
                "commit": "abc123",
                "policyPath": str(verified_pack),
                "rolePath": str(tmp_path / "missing-roles.yaml"),
            },
        )
        assert status["result"]["status"] == "blocked"
        assert any(
            "'unrecorded'" in item and "FR-M42-05" in item
            for item in status["result"]["missing"]
        )


class TestRequiresVerifiedIdentityParsing:
    def test_boolean_forms(self):
        assert policy.parse_policy_pack(
            PACK_BASE + "requiresVerifiedIdentity: true\n", "t"
        ).requires_verified_identity("main") is True
        pack = policy.parse_policy_pack(PACK_BASE, "t")
        assert pack.requires_verified_identity("main") is False

    def test_mapping_form_and_per_branch_override(self):
        pack = policy.parse_policy_pack(PACK_VERIFIED_PER_BRANCH, "t")
        assert pack.errors == []
        assert pack.requires_verified_identity("main") is True
        assert pack.requires_verified_identity("feature") is False
        assert pack.requires_verified_identity(None) is False

    def test_invalid_shapes_fail_closed(self):
        bad_type = policy.parse_policy_pack(
            PACK_BASE + "requiresVerifiedIdentity: yes please\n", "t"
        )
        assert bad_type.fail_closed
        bad_branch = policy.parse_policy_pack(
            PACK_BASE
            + "requiresVerifiedIdentity:\n  branches:\n    main: sometimes\n",
            "t",
        )
        assert bad_branch.fail_closed
        bad_key = policy.parse_policy_pack(
            PACK_BASE + "requiresVerifiedIdentity:\n  everywhere: true\n", "t"
        )
        assert bad_key.fail_closed


# -- FR-M42-06/SEC-31/AC-46/NFR-36 (T08): revocation -------------------------


class TestRevocation:
    def test_identity_revoke_records_the_row_before_returning(self, tmp_path, repo):
        server = make_server(tmp_path, repo, GRACE_VERIFIED)
        response = call(
            server,
            2,
            "identity.revoke",
            {"email": "ada@example.com", "reason": "offboarding"},
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["recorded"] is True
        assert result["email"] == "ada@example.com"
        row = server.ledger.query(action_type="identity_revocation", limit=10)[0]
        assert row["decision"] == "revoked"
        assert row["seq"] == result["sequence"]
        detail = read_detail(server, row["seq"])
        assert detail["revokedAt"] == result["revokedAt"]
        assert revocations.revoked_at(server.ledger, "ada@example.com") == (
            result["revokedAt"]
        )

    def test_new_approval_refused_from_the_instant_of_revocation(
        self, tmp_path, repo
    ):
        # AC-46/NFR-36: the refusal is effective from the instant the
        # revocation row commits — in-process there is no propagation
        # delay; the five minutes bound other replicas only.
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        before = call(
            server, 2, "gate.approve", {"subject": "main", "commit": "abc123"}
        )
        assert "error" not in before, before
        revoked = call(
            server,
            3,
            "identity.revoke",
            {"email": "ada@example.com", "revokedAt": "2030-01-01T00:00:00Z"},
        )
        assert "error" not in revoked, revoked
        refused = call(
            server, 4, "gate.approve", {"subject": "main", "commit": "def456"}
        )
        assert "error" in refused
        assert refused["error"]["data"]["code"] == "IDENTITY_REVOKED"
        # The refusal names the recorded revokedAt instant.
        assert "2030-01-01T00:00:00Z" in refused["error"]["message"]
        approvals = server.ledger.query(action_type="approval", limit=10)
        # Only the pre-revocation approval exists; nothing was recorded by
        # the refused attempt.
        assert len(approvals) == 1

    def test_revocation_stops_an_in_flight_merge(self, tmp_path, repo):
        # SEC-31: a session valid at issue SHALL NOT authorise a merge
        # after its identity has been revoked — the gate re-checks the
        # binding at execution.
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        call(server, 2, "gate.approve", {"subject": "main", "commit": "abc123"})
        clear = call(server, 3, "gate.status", {"subject": "main", "commit": "abc123"})
        assert clear["result"]["status"] == "approved"
        call(
            server,
            4,
            "identity.revoke",
            # Back-dated before the approval: revocation binds regardless
            # of when the approval was recorded.
            {"email": "ada@example.com", "revokedAt": "2020-01-01T00:00:00Z"},
        )
        blocked = call(
            server, 5, "gate.status", {"subject": "main", "commit": "abc123"}
        )
        assert blocked["result"]["status"] == "blocked"
        assert any(
            "revoked at 2020-01-01T00:00:00Z" in item and "SEC-31" in item
            for item in blocked["result"]["missing"]
        )

    def test_revocation_blocks_an_in_flight_authorisation(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        call(server, 2, "gate.approve", {"subject": "main", "commit": "abc123"})
        ledger = server.ledger
        pack = policy.parse_policy_pack(PACK_BASE, "t")
        keys = EphemeralSigningKeyProvider()
        authorisation = merge_authorisation.issue_authorisation(
            keys,
            repository="acme/widgets",
            subject="main",
            base_commit="base1",
            head_commit="abc123",
            digest="digest1",
            policy_version="governance/v2",
            evidence=["tests-pass"],
            approver="Ada Lovelace <ada@example.com>",
            approved_by_class="human_individual",
            issued_at="2029-06-01T00:00:00Z",
            expires_at="2030-06-01T00:00:00Z",
        )
        binding = merge_authorisation.MergeBinding(
            repository="acme/widgets",
            subject="main",
            base_commit="base1",
            head_commit="abc123",
            diff_digest="digest1",
            policy_version="governance/v2",
            evidence=frozenset({"tests-pass"}),
            now="2030-01-01T00:00:00Z",
        )
        clear = merge_gate.check_merge(
            ledger,
            pack,
            subject="main",
            head_commit="abc123",
            authorisation=authorisation,
            binding=binding,
        )
        assert clear.allowed, clear.missing
        revocations.record_revocation(
            ledger,
            email="ada@example.com",
            revoked_by="Grace Hopper <grace@example.com>",
            reason="AC-46",
            revoked_at="2029-12-01T00:00:00Z",
        )
        blocked = merge_gate.check_merge(
            ledger,
            pack,
            subject="main",
            head_commit="abc123",
            authorisation=authorisation,
            binding=binding,
        )
        assert not blocked.allowed
        # The authorisation's own fields are untouched — it dies purely
        # because its approver's identity was revoked.
        assert any("revoked at 2029-12-01T00:00:00Z" in note for note in blocked.missing)
        assert any("SEC-31" in note for note in blocked.missing)

    def test_reinstatement_clears_the_revocation(self, tmp_path, repo):
        server = make_server(tmp_path, repo, ADA_VERIFIED)
        call(server, 2, "identity.revoke", {"email": "ada@example.com"})
        blocked = call(server, 3, "gate.approve", {"subject": "main", "commit": "a"})
        assert "error" in blocked
        server.ledger.append(
            {
                "story_id": "identity:ada@example.com",
                "phase": "review",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_version": "0",
                "actor_kind": "meta",
                "policy_version": "governance/v2",
                "action_type": "identity_revocation",
                "decision": "reinstated",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "input": json.dumps(
                    {"method": "identity.reinstate", "email": "ada@example.com"}
                ),
            }
        )
        assert revocations.revoked_at(server.ledger, "ada@example.com") is None
        accepted = call(server, 4, "gate.approve", {"subject": "main", "commit": "a"})
        assert "error" not in accepted, accepted

    def test_revoke_validates_its_params(self, tmp_path, repo):
        server = make_server(tmp_path, repo, GRACE_VERIFIED)
        bad = call(server, 2, "identity.revoke", {"email": "not-an-email"})
        assert "error" in bad
        assert server.ledger.query(action_type="identity_revocation", limit=10) == []


# -- the shipped pack shape stays loadable -----------------------------------


def test_shipped_governance_pack_parses_with_the_new_key():
    pack = policy.load_policy_pack(
        [Path(__file__).parents[2] / "policy" / "governance.yaml"]
    )
    assert pack.errors == []
    assert pack.requires_verified_identity("main") is False
