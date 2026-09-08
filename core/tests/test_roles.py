"""Roles, SoD, N-of-M, delegation and approval hygiene (FR-M20-02…08;
F1 Workstream C task 16).

The role pack (policy/roles.yaml, fail-closed like the governance pack)
defines the FR-M20-02 roles — Engineer, Reviewer, Approver, Governor,
Auditor — and maps them to permitted gate actions. The merge gate consumes
it: a role that may not approve gets a structured refusal (never a silent
skip); separation of duties (FR-M20-03) refuses the identity that ingested
a change approving its own merge gate; N-of-M (FR-M20-04) counts distinct
recorded approvers against the protected branch's threshold; delegation
(FR-M20-05) grants an approval right to another principal with expiry,
ledger-recorded, chain-bounded and cycle-free; approval hygiene (FR-M20-06)
surfaces rubber-stamping signals — sub-threshold approve latency, approver
== requester, back-to-back bulk approvals — as warnings in the gate status
payload, measured from ledger history (the F2 measurement hook).

Attack cases are the point: self-approval, expired delegation, delegation
cycle, insufficient N approvals.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import merge_gate, policy, roles
from meridian_core.identity import ResolvedIdentity
from meridian_core.ledger.core import Ledger, utc_now
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

FIXTURE = Path(__file__).parent / "fixtures" / "gh_api" / "pull_41_detail.json"

ROLES_TEXT = """
version: 1
defaultRole: approver
roles:
  engineer:
    description: Authors changes.
    permissions: []
  reviewer:
    description: Reviews.
    permissions: [approve]
  approver:
    description: Approves.
    permissions: [approve, delegate]
  governor:
    description: Runs governance.
    permissions: [approve, halt, policy-change, delegate]
  auditor:
    description: Reads everything, changes nothing.
    permissions: [export-audit]
    readOnly: true
approvals:
  nOfM:
    main: 2
soD:
  forbidSelfApproval: true
delegation:
  maxChainDepth: 2
  maxTtlDays: 30
hygiene:
  approveLatencyFloorSeconds: 30
  bulkWindowMinutes: 10
  bulkMinCount: 3
"""

GOVERNANCE_TEXT = """
version: 2
protectedBranches: [main]
profiles: {}
"""

ADA = ResolvedIdentity(
    id="ada@example.com", display_name="Ada Lovelace",
    email="ada@example.com", assurance="local",
)
GRACE = ResolvedIdentity(
    id="grace@example.com", display_name="Grace Hopper",
    email="grace@example.com", assurance="local",
)
ALAN = ResolvedIdentity(
    id="alan@example.com", display_name="Alan Turing",
    email="alan@example.com", assurance="local",
)


class SwitchableProvider:
    """Tests switch the acting human between RPCs (delegation chains, SoD)."""

    def __init__(self, value: ResolvedIdentity) -> None:
        self.value = value

    def resolve(self) -> ResolvedIdentity:
        return self.value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
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


@pytest.fixture()
def role_pack() -> roles.RolePack:
    return roles.parse_role_pack(ROLES_TEXT, "test-roles")


@pytest.fixture()
def governance_pack() -> policy.PolicyPack:
    return policy.parse_policy_pack(GOVERNANCE_TEXT, "test-governance")


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


@pytest.fixture()
def role_path(tmp_path: Path) -> Path:
    target = tmp_path / "roles.yaml"
    target.write_text(ROLES_TEXT, encoding="utf-8")
    return target


@pytest.fixture()
def governance_path(tmp_path: Path) -> Path:
    target = tmp_path / "governance.yaml"
    target.write_text(GOVERNANCE_TEXT, encoding="utf-8")
    return target


def make_server(tmp_path: Path, repo: Path, who: ResolvedIdentity = ADA) -> SidecarServer:
    server = SidecarServer(
        ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()),
        identity_provider=SwitchableProvider(who),
    )
    response = server.handle_message(
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
    assert "result" in response
    return server


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def provider_of(server: SidecarServer) -> SwitchableProvider:
    return server._identity_provider  # noqa: SLF001 - test seam


def ingest_pr(server: SidecarServer, request_id: int, governance_path: Path) -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    response = call(
        server,
        request_id,
        "pr/ingest",
        {"pr": payload, "policyPath": str(governance_path)},
    )
    assert "result" in response, response
    return response["result"]


# -- role pack parsing (FR-M20-02; fail-closed) ---------------------------------


class TestRolePack:
    def test_valid_pack_parses_with_the_five_spec_roles(self) -> None:
        pack = roles.parse_role_pack(ROLES_TEXT, "test")
        assert pack.errors == []
        assert set(pack.roles) == {
            "engineer", "reviewer", "approver", "governor", "auditor"
        }
        assert pack.default_role == "approver"
        assert pack.roles["auditor"].read_only is True

    def test_repo_policy_roles_yaml_loads_clean(self) -> None:
        pack = roles.parse_role_pack(
            (Path(__file__).resolve().parent.parent.parent / "policy" / "roles.yaml")
            .read_text(encoding="utf-8"),
            "policy/roles.yaml",
        )
        assert pack.errors == []
        assert pack.roles["engineer"].may("approve") is False
        assert pack.roles["approver"].may("approve") is True
        assert pack.roles["governor"].may("policy-change") is True
        assert pack.roles["auditor"].may("approve") is False

    def test_unknown_top_level_section_fails_closed(self) -> None:
        pack = roles.parse_role_pack("version: 1\nbogus: {}\n", "bad")
        assert pack.fail_closed
        assert any("bogus" in error for error in pack.errors)

    def test_malformed_yaml_fails_closed(self) -> None:
        pack = roles.parse_role_pack("roles: [unclosed\n", "bad")
        assert pack.fail_closed

    def test_missing_file_loads_the_builtin_default(self, tmp_path: Path) -> None:
        # No roles.yaml anywhere: the built-in default keeps the gate
        # working (approver may approve, SoD on, n-of-m 1). A PRESENT but
        # malformed file fails closed instead — that distinction is policy.
        pack = roles.load_role_pack([tmp_path / "absent.yaml"])
        assert pack.errors == []
        assert pack.roles["approver"].may("approve") is True
        assert pack.sod_forbid_self_approval is True
        assert pack.n_of_m == {}

    def test_present_but_malformed_file_fails_closed(self, tmp_path: Path) -> None:
        broken = tmp_path / "roles.yaml"
        broken.write_text("roles: [unclosed\n", encoding="utf-8")
        pack = roles.load_role_pack([broken])
        assert pack.fail_closed

    def test_n_of_m_must_be_positive_integers(self) -> None:
        pack = roles.parse_role_pack(
            "version: 1\napprovals:\n  nOfM:\n    main: zero\n", "bad"
        )
        assert pack.fail_closed
        pack = roles.parse_role_pack(
            "version: 1\napprovals:\n  nOfM:\n    main: 0\n", "bad"
        )
        assert pack.fail_closed


# -- role checking for gate actions (FR-M20-02/07/08) ----------------------------


class TestCheckPermission:
    def test_approver_may_approve(self, role_pack: roles.RolePack) -> None:
        check = roles.check_permission(role_pack, "approver", "approve")
        assert check.permitted is True

    def test_engineer_may_not_approve_with_reason(self, role_pack: roles.RolePack) -> None:
        check = roles.check_permission(role_pack, "engineer", "approve")
        assert check.permitted is False
        assert "engineer" in check.reason
        assert "approver" in check.reason  # the permitted roles are named

    def test_only_governor_changes_policy(self, role_pack: roles.RolePack) -> None:
        assert roles.check_permission(role_pack, "governor", "policy-change").permitted
        for role in ("engineer", "reviewer", "approver", "auditor"):
            assert not roles.check_permission(role_pack, role, "policy-change").permitted

    def test_auditor_is_read_only_but_exports_audit_bundles(
        self, role_pack: roles.RolePack
    ) -> None:
        assert role_pack.roles["auditor"].read_only is True
        assert roles.check_permission(role_pack, "auditor", "export-audit").permitted
        for action in ("approve", "halt", "delegate", "policy-change"):
            assert not roles.check_permission(role_pack, "auditor", action).permitted

    def test_unknown_role_is_refused(self, role_pack: roles.RolePack) -> None:
        check = roles.check_permission(role_pack, "intern", "approve")
        assert check.permitted is False
        assert "intern" in check.reason

    def test_fail_closed_pack_refuses_everything(self) -> None:
        pack = roles.parse_role_pack("roles: [unclosed\n", "bad")
        check = roles.check_permission(pack, "approver", "approve")
        assert check.permitted is False
        assert pack.errors[0] in check.reason


# -- merge gate consumes the role pack: N-of-M (FR-M20-04) -----------------------


def append_approval(
    ledger: Ledger, subject: str, commit: str, who: ResolvedIdentity,
    role: str = "approver", ts: str | None = None,
) -> int:
    entry = {
        "ts_utc": ts or utc_now(),
        "story_id": f"gate:{subject}",
        "phase": "review",
        "loop_id": "governance",
        "loop_iteration": 1,
        "actor_id": "governor",
        "actor_kind": "meta",
        "actor_version": "test",
        "policy_version": "test",
        "action_type": "approval",
        "decision": "approved",
        "vendor": "meridian",
        "observation_confidence": "direct",
        "human_actor": who.display(),
        "human_role": role,
        "input": json.dumps({"method": "gate.approve", "subject": subject, "commit": commit, "role": role}),
    }
    return ledger.append(entry).sequence


class TestNofM:
    def test_single_approval_below_threshold_blocks(
        self, ledger: Ledger, governance_pack: policy.PolicyPack, role_pack: roles.RolePack
    ) -> None:
        append_approval(ledger, "main", "abc", ADA)
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="main", head_commit="abc",
            required_approvals=role_pack.n_of_m.get("main", 1),
        )
        assert verdict.allowed is False
        assert verdict.required_approvals == 2
        assert any("1/2" in item for item in verdict.missing)

    def test_two_distinct_approvers_pass(
        self, ledger: Ledger, governance_pack: policy.PolicyPack, role_pack: roles.RolePack
    ) -> None:
        append_approval(ledger, "main", "abc", ADA)
        append_approval(ledger, "main", "abc", GRACE)
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="main", head_commit="abc",
            required_approvals=role_pack.n_of_m.get("main", 1),
        )
        assert verdict.allowed is True
        assert len(verdict.approvals) == 2

    def test_same_approver_twice_is_one_approver(
        self, ledger: Ledger, governance_pack: policy.PolicyPack
    ) -> None:
        # N-of-M counts distinct humans — one person approving twice is
        # still one approver (that is the point of the rule).
        append_approval(ledger, "main", "abc", ADA)
        append_approval(ledger, "main", "abc", ADA, ts="2999-01-01T00:00:00Z")
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="main", head_commit="abc",
            required_approvals=2,
        )
        assert verdict.allowed is False

    def test_approval_with_disallowed_role_does_not_count(
        self, ledger: Ledger, governance_pack: policy.PolicyPack
    ) -> None:
        append_approval(ledger, "main", "abc", ADA, role="engineer")
        append_approval(ledger, "main", "abc", GRACE, role="approver")
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="main", head_commit="abc",
            required_approvals=2, permitted_roles={"approver", "reviewer", "governor"},
        )
        assert verdict.allowed is False
        assert any("engineer" in item for item in verdict.missing)

    def test_unprotected_branch_needs_no_approvals(
        self, ledger: Ledger, governance_pack: policy.PolicyPack
    ) -> None:
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="feature/x",
            required_approvals=99,
        )
        assert verdict.allowed is True


# -- separation of duties (FR-M20-03) --------------------------------------------


class TestSeparationOfDuties:
    def test_approval_by_ingester_does_not_count(
        self, ledger: Ledger, governance_pack: policy.PolicyPack
    ) -> None:
        # The attack: ingest a PR, then approve it yourself. The merge gate
        # must exclude the ingester's own approval.
        ledger.append(
            {
                "ts_utc": "2024-01-01T00:00:00Z",
                "story_id": "PROJ-1",
                "phase": "intake",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_kind": "meta",
        "actor_version": "test",
                "policy_version": "test",
                "action_type": "pr_ingest",
                "decision": "proposed",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "human_actor": ADA.display(),
                "input": json.dumps(
                    {
                        "method": "pr/ingest",
                        "subject": "pr:acme/payments#41",
                        "ingestedBy": ADA.wire(),
                    }
                ),
            }
        )
        append_approval(ledger, "pr:acme/payments#41", "abc", ADA)
        verdict = merge_gate.check_merge(
            ledger, governance_pack, subject="pr:acme/payments#41",
            head_commit="abc", requires_approval=True, required_approvals=1,
            excluded_identities={ADA.email},
        )
        assert verdict.allowed is False
        assert any("FR-M20-03" in item or "ingested" in item for item in verdict.missing)

    def test_gate_approve_refuses_the_self_approval_attack(
        self, tmp_path: Path, repo: Path, governance_path: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        subject = ingest_pr(server, 2, governance_path)["subject"]
        denied = call(
            server,
            3,
            "gate.approve",
            {
                "subject": subject,
                "commit": "abc",
                "role": "approver",
                "rolePath": str(role_path),
                "policyPath": str(governance_path),
            },
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "FR-M20-03" in denied["error"]["message"]
        assert denied["error"]["data"]["code"] == "SOD_SELF_APPROVAL"
        # The attack left no approval behind, and the merge stays blocked.
        assert server.ledger.query(action_type="approval", limit=10) == []
        status = call(server, 4, "pr/status", {"subject": subject, "policyPath": str(governance_path)})
        assert status["result"]["merge"]["status"] == "blocked"

    def test_different_human_approves_after_ingest(
        self, tmp_path: Path, repo: Path, governance_path: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        ingested = ingest_pr(server, 2, governance_path)
        subject = ingested["subject"]
        provider_of(server).value = GRACE
        approved = call(
            server,
            3,
            "gate.approve",
            {
                "subject": subject,
                "commit": ingested["headCommit"],
                "role": "approver",
                "rolePath": str(role_path),
                "policyPath": str(governance_path),
            },
        )
        assert approved["result"]["recorded"] is True
        status = call(server, 4, "pr/status", {"subject": subject, "policyPath": str(governance_path)})
        assert status["result"]["merge"]["status"] == "approved"


# -- role-checked gate.approve (FR-M20-02) ----------------------------------------


class TestGateApproveRoleChecking:
    def test_role_that_may_not_approve_gets_a_structured_refusal(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo)
        denied = call(
            server,
            2,
            "gate.approve",
            {"subject": "main", "commit": "abc", "role": "engineer", "rolePath": str(role_path)},
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        data = denied["error"]["data"]
        assert data["code"] == "ROLE_NOT_PERMITTED"
        assert data["role"] == "engineer"
        assert "approver" in data["permittedRoles"]
        # A refusal never records.
        assert server.ledger.query(action_type="approval", limit=10) == []

    def test_unknown_role_is_refused_when_policy_exists(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo)
        denied = call(
            server,
            2,
            "gate.approve",
            {"subject": "main", "commit": "abc", "role": "intern", "rolePath": str(role_path)},
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "intern" in denied["error"]["message"]

    def test_fail_closed_role_pack_refuses_every_approval(
        self, tmp_path: Path, repo: Path
    ) -> None:
        broken = tmp_path / "broken-roles.yaml"
        broken.write_text("roles: [unclosed\n", encoding="utf-8")
        server = make_server(tmp_path, repo)
        denied = call(
            server,
            2,
            "gate.approve",
            {"subject": "main", "commit": "abc", "role": "approver", "rolePath": str(broken)},
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "roles" in denied["error"]["message"].lower()

    def test_permitted_role_records_normally(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo)
        approved = call(
            server,
            2,
            "gate.approve",
            {"subject": "main", "commit": "abc", "role": "approver", "rolePath": str(role_path)},
        )
        assert approved["result"]["recorded"] is True


# -- N-of-M end to end through the RPCs (FR-M20-04) -------------------------------


class TestNofMRpc:
    def test_insufficient_approvals_block_then_threshold_passes(
        self, tmp_path: Path, repo: Path, governance_path: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        ingested = ingest_pr(server, 2, governance_path)
        subject = ingested["subject"]
        head = ingested["headCommit"]
        # SoD needs a different approver than the ingester; n-of-m needs two.
        provider_of(server).value = GRACE
        call(
            server, 3, "gate.approve",
            {"subject": subject, "commit": head, "role": "approver",
             "rolePath": str(role_path), "policyPath": str(governance_path)},
        )
        status = call(
            server, 4, "pr/status",
            {"subject": subject, "policyPath": str(governance_path), "rolePath": str(role_path)},
        )
        merge = status["result"]["merge"]
        assert merge["status"] == "blocked"
        assert merge["requiredApprovals"] == 2
        assert merge["approvalsReceived"] == 1
        assert any("1/2" in item for item in merge["missing"])

        provider_of(server).value = ALAN
        call(
            server, 5, "gate.approve",
            {"subject": subject, "commit": head, "role": "reviewer",
             "rolePath": str(role_path), "policyPath": str(governance_path)},
        )
        status = call(
            server, 6, "pr/status",
            {"subject": subject, "policyPath": str(governance_path), "rolePath": str(role_path)},
        )
        merge = status["result"]["merge"]
        assert merge["status"] == "approved"
        assert merge["approvalsReceived"] == 2


# -- delegation (FR-M20-05) -------------------------------------------------------


def delegate(
    server: SidecarServer, request_id: int, to: str, role: str = "approver",
    role_path: Path | None = None, expires_at: str | None = None,
    holder_role: str = "approver",
) -> dict:
    params: dict = {"to": to, "role": role, "holderRole": holder_role}
    if role_path is not None:
        params["rolePath"] = str(role_path)
    if expires_at is not None:
        params["expiresAt"] = expires_at
    return call(server, request_id, "roles/delegate", params)


class TestDelegation:
    def test_delegation_is_recorded_before_the_response(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        response = delegate(server, 2, to="grace@example.com", role_path=role_path)
        assert response["result"]["recorded"] is True
        rows = server.ledger.query(action_type="delegation", limit=10)
        assert len(rows) == 1
        detail = json.loads(
            server.ledger.read_blob(rows[0]["input_ref"], rows[0]["blob_key_id"]).decode("utf-8")
        )
        assert detail["from"]["email"] == "ada@example.com"
        assert detail["to"] == "grace@example.com"
        assert detail["role"] == "approver"
        assert detail["expiresAt"] > rows[0]["ts_utc"]

    def test_delegatee_can_approve_through_the_grant(
        self, tmp_path: Path, repo: Path, governance_path: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        ingest_pr(server, 2, governance_path)
        response = delegate(server, 3, to="grace@example.com", role_path=role_path)
        assert response["result"]["recorded"] is True
        # Grace holds no role; the active delegation grants her the right.
        provider_of(server).value = GRACE
        approved = call(
            server, 4, "gate.approve",
            {"subject": "pr:acme/payments#41", "commit": "abc", "role": "approver",
             "rolePath": str(role_path), "policyPath": str(governance_path)},
        )
        assert approved["result"]["recorded"] is True

    def test_expired_delegation_grants_nothing(self, ledger: Ledger) -> None:
        now = "2024-06-01T00:00:00Z"
        for seq, expires in ((1, "2023-01-01T00:00:00Z"), (2, "2025-01-01T00:00:00Z")):
            ledger.append(
                {
                    "ts_utc": f"2024-01-0{seq}T00:00:00Z",
                    "story_id": "delegation",
                    "phase": "review",
                    "loop_id": "governance",
                    "loop_iteration": 1,
                    "actor_id": "governor",
                    "actor_kind": "meta",
        "actor_version": "test",
                    "policy_version": "test",
                    "action_type": "delegation",
                    "decision": "delegated",
                    "vendor": "meridian",
                    "observation_confidence": "direct",
                    "human_actor": ADA.display(),
                    "input": json.dumps(
                        {
                            "method": "roles/delegate",
                            "from": ADA.wire(),
                            "to": "grace@example.com",
                            "role": "approver",
                            "expiresAt": expires,
                            "depth": 1,
                        }
                    ),
                }
            )
        grant = roles.find_active_delegation(ledger, "grace@example.com", "approver", now)
        assert grant is not None
        assert grant["expiresAt"] == "2025-01-01T00:00:00Z"
        # Past expiry: nothing.
        assert roles.find_active_delegation(ledger, "grace@example.com", "approver", "2026-01-01T00:00:00Z") is None

    def test_expired_expiry_is_refused_at_creation(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        denied = delegate(
            server, 2, to="grace@example.com", role_path=role_path,
            expires_at="2020-01-01T00:00:00Z",
        )
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "expired" in denied["error"]["message"]
        assert server.ledger.query(action_type="delegation", limit=10) == []

    def test_ttl_beyond_policy_max_is_refused(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        response = call(
            server, 2, "roles/delegate",
            {"to": "grace@example.com", "role": "approver", "ttlDays": 365,
             "rolePath": str(role_path)},
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "ttl" in response["error"]["message"].lower()

    def test_delegation_cycle_is_refused(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo, who=ADA)
        assert delegate(server, 2, to="grace@example.com", role_path=role_path)["result"]["recorded"]
        # Grace delegates back to Ada: a cycle, refused.
        provider_of(server).value = GRACE
        denied = delegate(server, 3, to="ada@example.com", role_path=role_path)
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "cycle" in denied["error"]["message"].lower()
        assert len(server.ledger.query(action_type="delegation", limit=10)) == 1

    def test_delegation_chain_depth_is_bounded(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        # maxChainDepth 2: Ada -> Grace (1), Grace -> Alan (2), Alan -> Ed (3) refused.
        server = make_server(tmp_path, repo, who=ADA)
        assert delegate(server, 2, to="grace@example.com", role_path=role_path)["result"]["recorded"]
        provider_of(server).value = GRACE
        response = delegate(server, 3, to="alan@example.com", role_path=role_path)
        assert response["result"]["delegation"]["depth"] == 2
        provider_of(server).value = ALAN
        denied = delegate(server, 4, to="ed@example.com", role_path=role_path)
        assert denied["error"]["code"] == protocol.INVALID_PARAMS
        assert "depth" in denied["error"]["message"].lower()


# -- approval hygiene (FR-M20-06) --------------------------------------------------


def _approval_row(who: ResolvedIdentity, ts: str, subject: str = "main") -> dict:
    return {
        "ts_utc": ts,
        "story_id": f"gate:{subject}",
        "phase": "review",
        "loop_id": "governance",
        "loop_iteration": 1,
        "actor_id": "governor",
        "actor_kind": "meta",
        "actor_version": "test",
        "policy_version": "test",
        "action_type": "approval",
        "decision": "approved",
        "vendor": "meridian",
        "observation_confidence": "direct",
        "human_actor": who.display(),
        "human_role": "approver",
        "input": json.dumps(
            {"method": "gate.approve", "subject": subject, "commit": "abc", "role": "approver"}
        ),
    }


class TestApprovalHygiene:
    def _pack(self) -> roles.RolePack:
        return roles.parse_role_pack(ROLES_TEXT, "test")

    def test_sub_threshold_latency_warns(self, ledger: Ledger) -> None:
        # Gate opened at :00; approved 5s later — under the 30s floor.
        ledger.append(
            {
                "ts_utc": "2024-01-01T00:00:00Z",
                "story_id": "PROJ-1",
                "phase": "intake",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_kind": "meta",
        "actor_version": "test",
                "policy_version": "test",
                "action_type": "pr_ingest",
                "decision": "proposed",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "input": json.dumps({"method": "pr/ingest", "subject": "pr:r#1"}),
            }
        )
        ledger.append(_approval_row(ADA, "2024-01-01T00:00:05Z", subject="pr:r#1"))
        warnings = roles.assess_hygiene(ledger, self._pack(), subject="pr:r#1")
        assert any("latency" in warning for warning in warnings)

    def test_reasonable_latency_is_silent(self, ledger: Ledger) -> None:
        ledger.append(
            {
                "ts_utc": "2024-01-01T00:00:00Z",
                "story_id": "PROJ-1",
                "phase": "intake",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_kind": "meta",
        "actor_version": "test",
                "policy_version": "test",
                "action_type": "pr_ingest",
                "decision": "proposed",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "input": json.dumps({"method": "pr/ingest", "subject": "pr:r#1"}),
            }
        )
        ledger.append(_approval_row(ADA, "2024-01-01T02:00:00Z", subject="pr:r#1"))
        assert roles.assess_hygiene(ledger, self._pack(), subject="pr:r#1") == []

    def test_approver_equals_requester_warns(self, ledger: Ledger) -> None:
        ledger.append(
            {
                "ts_utc": "2024-01-01T00:00:00Z",
                "story_id": "PROJ-1",
                "phase": "intake",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_kind": "meta",
        "actor_version": "test",
                "policy_version": "test",
                "action_type": "pr_ingest",
                "decision": "proposed",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "human_actor": ADA.display(),
                "input": json.dumps(
                    {"method": "pr/ingest", "subject": "pr:r#1", "ingestedBy": ADA.wire()}
                ),
            }
        )
        ledger.append(_approval_row(ADA, "2024-01-01T01:00:00Z", subject="pr:r#1"))
        warnings = roles.assess_hygiene(ledger, self._pack(), subject="pr:r#1")
        assert any("requester" in warning for warning in warnings)

    def test_back_to_back_bulk_approvals_warn(self, ledger: Ledger) -> None:
        for index in range(3):
            ledger.append(
                _approval_row(ADA, f"2024-01-01T00:0{index}:00Z", subject=f"pr:r#{index}")
            )
        warnings = roles.assess_hygiene(ledger, self._pack(), subject="pr:r#0")
        assert any("bulk" in warning for warning in warnings)

    def test_hygiene_warnings_surface_in_gate_status(
        self, tmp_path: Path, repo: Path, governance_path: Path, role_path: Path
    ) -> None:
        # The F2 hook: rubber-stamping signals ride the gate status payload.
        server = make_server(tmp_path, repo, who=ADA)
        subject = ingest_pr(server, 2, governance_path)["subject"]
        provider_of(server).value = GRACE
        call(
            server, 3, "gate.approve",
            {"subject": subject, "commit": "abc", "role": "approver",
             "rolePath": str(role_path), "policyPath": str(governance_path)},
        )
        status = call(
            server, 4, "gate.status",
            {"subject": subject, "commit": "abc",
             "rolePath": str(role_path), "policyPath": str(governance_path)},
        )
        warnings = status["result"]["hygieneWarnings"]
        assert any("latency" in warning for warning in warnings)


# -- roles/list and roles/check RPCs (FR-M20-02) -----------------------------------


class TestRolesRpcs:
    def test_roles_list_returns_the_pack(self, tmp_path: Path, repo: Path, role_path: Path) -> None:
        server = make_server(tmp_path, repo)
        response = call(server, 2, "roles/list", {"rolePath": str(role_path)})
        result = response["result"]
        assert result["failClosed"] is False
        names = {role["name"] for role in result["roles"]}
        assert names == {"engineer", "reviewer", "approver", "governor", "auditor"}
        auditor = next(role for role in result["roles"] if role["name"] == "auditor")
        assert auditor["readOnly"] is True
        assert result["approvals"]["nOfM"] == {"main": 2}

    def test_roles_list_fail_closed_pack_reports_errors(
        self, tmp_path: Path, repo: Path
    ) -> None:
        broken = tmp_path / "broken.yaml"
        broken.write_text("roles: [unclosed\n", encoding="utf-8")
        server = make_server(tmp_path, repo)
        response = call(server, 2, "roles/list", {"rolePath": str(broken)})
        assert response["result"]["failClosed"] is True
        assert response["result"]["errors"]

    def test_roles_check_permitted_and_refused(
        self, tmp_path: Path, repo: Path, role_path: Path
    ) -> None:
        server = make_server(tmp_path, repo)
        ok = call(server, 2, "roles/check", {"role": "approver", "action": "approve", "rolePath": str(role_path)})
        assert ok["result"]["permitted"] is True
        denied = call(server, 3, "roles/check", {"role": "engineer", "action": "approve", "rolePath": str(role_path)})
        assert denied["result"]["permitted"] is False
        assert "approver" in denied["result"]["reason"]

    def test_roles_check_fail_closed_refuses(
        self, tmp_path: Path, repo: Path
    ) -> None:
        broken = tmp_path / "broken.yaml"
        broken.write_text("roles: [unclosed\n", encoding="utf-8")
        server = make_server(tmp_path, repo)
        response = call(server, 2, "roles/check", {"role": "approver", "action": "approve", "rolePath": str(broken)})
        assert response["result"]["permitted"] is False

    def test_governor_tier_disabled_refuses_roles_rpcs(
        self, tmp_path: Path, repo: Path
    ) -> None:
        server = SidecarServer(
            ledger=Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        )
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "tiers": ["flight-recorder"],
                    "workspaceDir": str(repo),
                },
            }
        )
        for request_id, method in ((2, "roles/list"), (3, "roles/check"), (4, "roles/delegate")):
            params = {} if method == "roles/list" else (
                {"role": "approver", "action": "approve"} if method == "roles/check"
                else {"to": "x@example.com", "role": "approver"}
            )
            response = call(server, request_id, method, params)
            assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED, method
