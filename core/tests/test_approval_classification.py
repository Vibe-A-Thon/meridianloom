"""Approval classification (FR-M42-07/08, FR-M12-07 AMD, AC-44; N1-T18/19).

D40 (closed): a versioned, Meridian-owned approval-class vocabulary —
v1 classes ``human_individual``, ``human_delegated``, ``bot_agent``,
``ruleset_actor``, ``unknown``. Every approval (gate.approve) and every
permission decision (acp/permissionDecision) is stamped with its class +
classifier version; a non-human class never satisfies a human-approval
policy and never counts as a human approval in any metric. The four
AC-44 cases — an auto-mode classifier verdict, a policy allow-rule, an
agent code-review approval, a ruleset bypass actor — are each recorded
with the correct class and proven not to satisfy the merge gate.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import approval_class, merge_gate, policy
from meridian_core.governance.identity import HumanIdentity
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles:
  review:
    criteria:
      - id: lead-approval
        kind: humanApproval
        roles: [lead]
"""

ROLES_TEXT = """
version: 1
defaultRole: contributor
roles:
  approver:
    permissions: [approve, delegate]
  contributor:
    permissions: []
delegation:
  maxChainDepth: 2
  maxTtlDays: 30
"""

APPROVER = HumanIdentity(name="Ada Lovelace", email="ada@example.com")


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "Fixture")
    env.setdefault("GIT_AUTHOR_EMAIL", "fixture@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Fixture")
    env.setdefault("GIT_COMMITTER_EMAIL", "fixture@example.com")
    result = subprocess.run(
        [
            "git",
            "-c", "core.autocrlf=false",
            "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main",
            "-c", f"user.name={APPROVER.name}",
            "-c", f"user.email={APPROVER.email}",
            *args,
        ],
        cwd=repo,
        env=env,
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
    git(target, "config", "user.name", APPROVER.name)
    git(target, "config", "user.email", APPROVER.email)
    (target / "app.txt").write_text("one\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "initial")
    return target


@pytest.fixture()
def pack() -> policy.PolicyPack:
    parsed = policy.parse_policy_pack(PACK_TEXT, "test-pack")
    assert parsed.errors == []
    return parsed


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def make_server(tmp_path: Path, repo: Path) -> SidecarServer:
    (repo / ".meridian" / "policy").mkdir(parents=True, exist_ok=True)
    (repo / ".meridian" / "policy" / "governance.yaml").write_text(
        PACK_TEXT, encoding="utf-8"
    )
    (repo / ".meridian" / "policy" / "roles.yaml").write_text(
        ROLES_TEXT, encoding="utf-8"
    )
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
                "workspaceDir": str(repo),
                "tiers": ["flight-recorder", "governor"],
            },
        }
    )
    return server


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99):
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def append_approval(
    ledger: Ledger,
    subject: str,
    commit: str,
    human_actor: str,
    *,
    approved_by: dict | None = None,
    role: str = "approver",
) -> int:
    """The ledger shape gate.approve writes; ``approved_by`` is the
    FR-M42-07 stamp an external connector (or the capture path) records."""
    detail = {"method": "gate.approve", "subject": subject, "commit": commit, "role": role}
    if approved_by is not None:
        detail["approvedBy"] = approved_by
    result = ledger.append(
        {
            "story_id": f"gate:{subject}",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/v2",
            "action_type": "approval",
            "decision": "approved",
            "human_actor": human_actor,
            "human_role": role,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(detail),
        }
    )
    return result.sequence


def read_detail(server: SidecarServer, sequence: int) -> dict:
    row = server.ledger.get_entry(sequence)
    return json.loads(
        server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
    )


# -- the closed vocabulary and classifier (D40, FR-M42-07) ---------------------


class TestClassifier:
    def test_vocabulary_is_closed_and_versioned(self):
        assert approval_class.CLASSES == (
            "human_individual",
            "human_delegated",
            "ruleset_actor",
            "bot_agent",
            "unknown",
        )
        assert approval_class.CLASSIFIER_VERSION == "approvedBy/v1"
        assert approval_class.stamp("human_individual") == {
            "class": "human_individual",
            "classifierVersion": "approvedBy/v1",
        }

    def test_human_identity_classifies_individual(self):
        assert (
            approval_class.classify("Ada Lovelace", "ada@example.com")
            == "human_individual"
        )

    def test_bot_markers_classify_bot_agent(self):
        # The SCM [bot] marker convention, a vendor code-review bot email.
        assert approval_class.classify("dependabot[bot]", "") == "bot_agent"
        assert (
            approval_class.classify("GitHub Copilot", "copilot@github.com")
            == "bot_agent"
        )

    def test_ruleset_markers_classify_ruleset_actor(self):
        assert approval_class.classify("repo-ruleset-bypass", "") == "ruleset_actor"
        assert approval_class.classify("branch ruleset", "") == "ruleset_actor"

    def test_empty_identity_is_unknown_never_invented(self):
        assert approval_class.classify("", "") == "unknown"

    def test_declared_closed_member_wins(self):
        assert (
            approval_class.classify("", "", declared="bot_agent") == "bot_agent"
        )

    def test_vendor_invented_types_map_onto_the_closed_set(self):
        # FR-M42-07's draft names and SCM actor types all find a closed-set
        # home at capture time (D40 mapping).
        assert approval_class.map_vendor_type("Bot") == "bot_agent"
        assert approval_class.map_vendor_type("Integration") == "bot_agent"
        assert approval_class.map_vendor_type("User") == "human_individual"
        assert approval_class.map_vendor_type("policy_rule") == "ruleset_actor"
        assert approval_class.map_vendor_type("bypass_actor") == "ruleset_actor"
        assert approval_class.map_vendor_type("model_classifier") == "bot_agent"
        assert (
            approval_class.classify("", "", declared="model_classifier")
            == "bot_agent"
        )

    def test_unmapped_vendor_path_is_unknown_p26(self):
        # A vendor-invented path that maps onto nothing is unknown — never
        # a residual, never invented, and never human by default.
        assert approval_class.map_vendor_type("fancy-new-thing") == "unknown"
        assert approval_class.classify("", "", declared="fancy-new-thing") == "unknown"

    def test_human_classes_satisfy_human_policy(self):
        assert approval_class.is_human_class("human_individual") is True
        assert approval_class.is_human_class("human_delegated") is True
        for cls in ("bot_agent", "ruleset_actor", "unknown"):
            assert approval_class.is_human_class(cls) is False


# -- T18: every approval and permission decision carries the class -------------


class TestApprovalStamping:
    def test_gate_approve_stamps_human_individual(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        commit = git(repo, "rev-parse", "main").strip()
        response = call(
            server, "gate.approve", {"subject": "main", "commit": commit, "role": "approver"}
        )
        assert response["result"]["approvedBy"] == {
            "class": "human_individual",
            "classifierVersion": "approvedBy/v1",
        }
        detail = read_detail(server, response["result"]["sequence"])
        assert detail["approvedBy"]["class"] == "human_individual"
        assert detail["approvedBy"]["classifierVersion"] == "approvedBy/v1"

    def test_delegated_approval_stamps_human_delegated(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        commit = git(repo, "rev-parse", "main").strip()
        # FR-M20-05: a delegation grant lets Ada approve holding a role
        # that does not itself carry the approve permission.
        server.ledger.append(
            {
                "story_id": "roles:delegation",
                "phase": "review",
                "loop_id": "governance",
                "loop_iteration": 1,
                "actor_id": "governor",
                "actor_version": "0",
                "actor_kind": "meta",
                "policy_version": "roles/v1",
                "action_type": "delegation",
                "decision": "delegated",
                "vendor": "meridian",
                "observation_confidence": "direct",
                "input": json.dumps(
                    {
                        "method": "roles/delegate",
                        "to": APPROVER.email,
                        "role": "contributor",
                        "expiresAt": "2999-01-01T00:00:00+00:00",
                    }
                ),
            }
        )
        response = call(
            server,
            "gate.approve",
            {"subject": "main", "commit": commit, "role": "contributor"},
        )
        assert response["result"]["approvedBy"]["class"] == "human_delegated"
        detail = read_detail(server, response["result"]["sequence"])
        assert detail["approvedBy"]["class"] == "human_delegated"

    def test_gate_status_carries_the_bound_approval_class(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        commit = git(repo, "rev-parse", "main").strip()
        call(server, "gate.approve", {"subject": "main", "commit": commit, "role": "approver"})
        response = call(
            server, "gate.status", {"subject": "main", "commit": commit}
        )
        assert response["result"]["status"] == "approved"
        assert response["result"]["approvedBy"] == {
            "class": "human_individual",
            "classifierVersion": "approvedBy/v1",
        }

    def test_permission_decision_selected_is_human_individual(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        response = call(
            server,
            "acp/permissionDecision",
            {"sessionId": "s1", "outcome": "selected", "optionId": "allow"},
        )
        assert response["result"] == {"recorded": True}
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        assert detail["approvedBy"]["class"] == "human_individual"

    def test_permission_decision_denied_by_policy_is_ruleset_actor(
        self, tmp_path, repo
    ):
        server = make_server(tmp_path, repo)
        call(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "s1",
                "outcome": "denied_by_policy",
                "reason": "allow-list",
            },
        )
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        # The policy gate decided; the human never saw the prompt.
        assert detail["approvedBy"]["class"] == "ruleset_actor"

    def test_permission_decision_vendor_class_hint_maps_at_capture(
        self, tmp_path, repo
    ):
        server = make_server(tmp_path, repo)
        call(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "s1",
                "outcome": "selected",
                "approvedByClass": "Bot",
            },
        )
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        assert detail["approvedBy"]["class"] == "bot_agent"

    def test_permission_decision_unmapped_hint_is_unknown(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        call(
            server,
            "acp/permissionDecision",
            {
                "sessionId": "s1",
                "outcome": "selected",
                "approvedByClass": "vendor-invented-path",
            },
        )
        row = server.ledger.query(action_type="permission_decision")[-1]
        detail = read_detail(server, row["seq"])
        assert detail["approvedBy"]["class"] == "unknown"


# -- T19 / AC-44: a non-human approval never counts ----------------------------


class TestNonHumanNeverCounts:
    def test_human_approval_still_satisfies_the_gate(self, ledger, pack):
        append_approval(ledger, "main", "a" * 40, APPROVER.display())
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is True
        assert verdict.approval is not None
        assert verdict.approval.approved_by_class == "human_individual"

    def test_pre_stamp_human_row_classifies_at_read_time(self, ledger, pack):
        # Rows written before the stamp existed carry no approvedBy block;
        # the gate classifies the recorded identity at read time.
        append_approval(ledger, "main", "a" * 40, APPROVER.display())
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is True
        assert verdict.approval.approved_by_class_version == "approvedBy/v1"

    def test_agent_code_review_approval_never_counts(self, ledger, pack):
        # AC-44 case: a vendor code-review bot (Copilot) approves the PR.
        # No stamp — the gate classifies the recorded identity itself.
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "GitHub Copilot <copilot@github.com>",
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.approval is None
        assert verdict.approvals == ()
        assert any("FR-M42-08" in note for note in verdict.missing)
        assert any("bot_agent" in note for note in verdict.missing)

    def test_ruleset_bypass_actor_never_counts(self, ledger, pack):
        # AC-44 case: a repository ruleset bypass actor is recorded.
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "repo-ruleset-bypass-actor",
            approved_by=approval_class.stamp("ruleset_actor"),
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.approvals == ()
        assert any("ruleset_actor" in note for note in verdict.missing)

    def test_policy_allow_rule_never_counts(self, ledger, pack):
        # AC-44 case: a policy allow-rule recorded as the approver (a
        # policy-rule path maps onto ruleset_actor in the closed set).
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "policy-allow-rule",
            approved_by={
                "class": "ruleset_actor",
                "classifierVersion": "approvedBy/v1",
            },
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.approvals == ()

    def test_classifier_verdict_never_counts(self, ledger, pack):
        # AC-44 case: an auto-mode classifier verdict recorded with the
        # bot_agent class it maps to.
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "auto-mode-classifier",
            approved_by={"class": "bot_agent", "classifierVersion": "approvedBy/v1"},
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.approvals == ()

    def test_unknown_class_never_counts(self, ledger, pack):
        # P26: an unclassifiable approval is unknown, and unknown is not
        # human — it never satisfies a human-approval policy.
        append_approval(
            ledger,
            "main",
            "a" * 40,
            APPROVER.display(),
            approved_by={"class": "unknown", "classifierVersion": "approvedBy/v1"},
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.approvals == ()

    def test_non_human_approval_absent_from_status_metric(self, ledger, pack):
        # FR-M42-08's metric half: approvalsReceived counts only valid
        # (human) approvals — the bot approval appears in neither the
        # verdict count nor the status payload.
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "GitHub Copilot <copilot@github.com>",
        )
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.approvals == ()
        assert len({a.approver.email for a in verdict.approvals}) == 0

    def test_collect_approvals_note_names_seq_and_class(self, ledger, pack):
        append_approval(
            ledger,
            "main",
            "a" * 40,
            "dependabot[bot]",
        )
        approvals, notes = merge_gate.collect_approvals(ledger, "main", "a" * 40)
        assert approvals == []
        assert any("dependabot[bot]" in note and "bot_agent" in note for note in notes)
