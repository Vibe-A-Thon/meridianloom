"""Merge gate (FR-M12-05, FR-M12-07; F1 Workstream B task 10).

No merge to a protected branch without a recorded human approval; the
approver identity is in the ledger and anonymous approval is impossible.
The protected-branch rule lives in governance/merge_gate.py as a check
function CI/SCM callers invoke (task 12 wires the connectors); here it is
proven against fixture repositories:

* a merge attempt without approval is refused with the missing-criteria
  report;
* with an approval recorded (gate.approve RPC), the merge passes and
  gate.status returns the approval's ledger sequence;
* the approval binds the commit digest — a changed head invalidates it;
* a governance halt of scope merge blocks merges (task 11's RPC records
  such entries; here the rows are appended directly);
* FR-M10-08: the approval lands in the ledger BEFORE gate.approve returns;
* FR-M12-07: the approving human identity (git user.name/email per D9) is
  recorded; without an identity the approval is refused, never anonymous;
* G5: governor disabled -> TIER_DISABLED, recorder untouched.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.governance import identity, merge_gate, policy
from meridian_core.governance.identity import GitIdentityProvider, StaticIdentityProvider
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

APPROVER = identity.HumanIdentity(name="Ada Lovelace", email="ada@example.com")


def git(repo: Path, *args: str, env_extra: dict | None = None) -> str:
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "Fixture")
    env.setdefault("GIT_AUTHOR_EMAIL", "fixture@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Fixture")
    env.setdefault("GIT_COMMITTER_EMAIL", "fixture@example.com")
    if env_extra:
        env.update(env_extra)
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
    """A fixture repository with main and a feature branch, two commits."""
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init")
    git(target, "config", "user.name", APPROVER.name)
    git(target, "config", "user.email", APPROVER.email)
    (target / "app.txt").write_text("one\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "initial")
    git(target, "checkout", "-b", "feature/story-1")
    (target / "app.txt").write_text("one\ntwo\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "story work")
    git(target, "checkout", "main")
    return target


@pytest.fixture()
def pack() -> policy.PolicyPack:
    parsed = policy.parse_policy_pack(PACK_TEXT, "test-pack")
    assert parsed.errors == []
    return parsed


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())


def head(repo: Path, branch: str = "feature/story-1") -> str:
    return git(repo, "rev-parse", branch).strip()


def append_approval(
    ledger: Ledger, subject: str, commit: str, approver=APPROVER, role: str = "lead"
) -> int:
    """The ledger shape gate.approve writes (the RPC is exercised below)."""
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
            "human_actor": approver.display(),
            "human_role": role,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(
                {"method": "gate.approve", "subject": subject, "commit": commit, "role": role}
            ),
        }
    )
    return result.sequence


def append_halt(ledger: Ledger, reason: str, subject: str | None = None) -> int:
    result = ledger.append(
        {
            "story_id": "gate:halt",
            "phase": "review",
            "loop_id": "governance",
            "loop_iteration": 1,
            "actor_id": "governor",
            "actor_version": "0",
            "actor_kind": "meta",
            "policy_version": "governance/v2",
            "action_type": "gate",
            "decision": "halted",
            "rework_reason": reason,
            "vendor": "meridian",
            "observation_confidence": "direct",
            "input": json.dumps(
                {"method": "gate.halt", "scope": "merge", "subject": subject, "reason": reason}
            ),
        }
    )
    return result.sequence


# -- identity (D9) ------------------------------------------------------------


class TestIdentity:
    def test_git_identity_provider_reads_user_config(self, repo):
        git(repo, "config", "user.name", APPROVER.name)
        git(repo, "config", "user.email", APPROVER.email)
        assert GitIdentityProvider(repo).identity() == APPROVER

    def test_missing_identity_is_an_error_never_anonymous(self, repo):
        # Empty repo-local values override any global identity: the repo
        # has no identity of its own, like a fresh CI checkout.
        git(repo, "config", "user.name", "")
        git(repo, "config", "user.email", "")
        with pytest.raises(identity.IdentityUnavailableError):
            GitIdentityProvider(repo).identity()

    def test_static_provider_for_injection(self):
        assert StaticIdentityProvider(APPROVER).identity() == APPROVER


# -- the check function --------------------------------------------------------


class TestCheckMerge:
    def test_unprotected_branch_needs_no_approval(self, repo, ledger, pack):
        verdict = merge_gate.check_merge(
            ledger, pack, subject="feature/story-1", head_commit=head(repo)
        )
        assert verdict.allowed is True
        assert verdict.required_approval is False
        assert verdict.approval is None

    def test_protected_branch_without_approval_is_refused_with_report(
        self, repo, ledger, pack
    ):
        verdict = merge_gate.check_merge(
            ledger, pack, subject="main", head_commit=head(repo)
        )
        assert verdict.allowed is False
        assert verdict.status == "blocked"
        assert verdict.required_approval is True
        assert any("no recorded human approval" in m for m in verdict.missing)

    def test_recorded_approval_allows_merge_with_sequence(
        self, repo, ledger, pack
    ):
        subject = "main"
        commit = head(repo)
        sequence = append_approval(ledger, subject, commit)
        verdict = merge_gate.check_merge(ledger, pack, subject=subject, head_commit=commit)
        assert verdict.allowed is True
        assert verdict.status == "approved"
        assert verdict.approval is not None
        assert verdict.approval.sequence == sequence
        assert verdict.approval.approver == APPROVER

    def test_changed_head_invalidates_the_approval(self, repo, ledger, pack):
        subject = "main"
        old_head = head(repo)
        append_approval(ledger, subject, old_head)
        # The PR gained a commit after approval: the binding digest differs.
        verdict = merge_gate.check_merge(
            ledger, pack, subject=subject, head_commit="0" * 40
        )
        assert verdict.allowed is False
        assert any("invalidated" in m for m in verdict.missing)
        assert old_head in verdict.missing[0]

    def test_fresher_approval_for_new_head_wins(self, repo, ledger, pack):
        subject = "main"
        old_head = head(repo)
        append_approval(ledger, subject, old_head)
        new_head = "1" * 40
        sequence = append_approval(ledger, subject, new_head)
        verdict = merge_gate.check_merge(
            ledger, pack, subject=subject, head_commit=new_head
        )
        assert verdict.allowed is True
        assert verdict.approval.sequence == sequence

    def test_anonymous_approval_row_does_not_count(self, ledger, pack):
        anonymous = identity.HumanIdentity(name="", email="")
        append_approval(ledger, "main", "a" * 40, approver=anonymous)
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert any("anonymous" in m for m in verdict.missing)

    def test_approval_for_another_branch_does_not_count(self, ledger, pack):
        append_approval(ledger, "develop", "a" * 40)
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False

    def test_merge_halt_blocks_with_reason(self, ledger, pack):
        append_halt(ledger, "incident: leaked credential", subject="main")
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.halted is True
        assert any("leaked credential" in m for m in verdict.missing)

    def test_halt_on_another_branch_does_not_block_this_one(self, ledger, pack):
        append_halt(ledger, "incident", subject="release/1.0")
        append_approval(ledger, "main", "a" * 40)
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is True

    def test_global_halt_without_subject_blocks_every_branch(self, ledger, pack):
        append_halt(ledger, "freeze all merges")
        verdict = merge_gate.check_merge(ledger, pack, subject="main", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.halted is True

    def test_fail_closed_pack_refuses_every_merge(self, ledger):
        broken = policy.fail_closed_pack("t", ["policy broken"])
        verdict = merge_gate.check_merge(ledger, broken, subject="feature/x", head_commit="a" * 40)
        assert verdict.allowed is False
        assert verdict.missing == ("policy broken",)


# -- RPC: gate.approve / gate.status -------------------------------------------


def make_server(
    tmp_path: Path, repo: Path, identity_provider=None
) -> SidecarServer:
    # The fixture repo IS the workspace: identity comes from its git
    # config (D9) and the pack from its .meridian/policy override.
    (repo / ".meridian" / "policy").mkdir(parents=True, exist_ok=True)
    (repo / ".meridian" / "policy" / "governance.yaml").write_text(
        PACK_TEXT, encoding="utf-8"
    )
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    server = SidecarServer(ledger=ledger, identity_provider=identity_provider)
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


class TestGateApproveRpc:
    def test_approval_records_identity_in_ledger_before_returning(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        commit = head(repo)
        response = call(
            server, "gate.approve", {"subject": "main", "commit": commit, "role": "lead"}
        )
        result = response["result"]
        assert result["recorded"] is True
        assert result["subject"] == "main"
        assert result["commit"] == commit
        assert result["approver"] == {"name": APPROVER.name, "email": APPROVER.email}
        # FR-M10-08: the row exists NOW, before any other call.
        row = server.ledger.get_entry(result["sequence"])
        assert row["action_type"] == "approval"
        assert row["decision"] == "approved"
        assert row["human_actor"] == APPROVER.display()
        assert row["human_role"] == "lead"
        detail = json.loads(
            server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8")
        )
        assert detail["subject"] == "main"
        assert detail["commit"] == commit

    def test_approval_unblocks_the_protected_branch(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        commit = head(repo)
        call(server, "gate.approve", {"subject": "main", "commit": commit, "role": "lead"})
        status = call(server, "gate.status", {"subject": "main", "commit": commit})["result"]
        assert status["status"] == "approved"
        assert status["approvalSequence"] > 0
        assert status["approver"]["email"] == APPROVER.email
        assert status["requiredApproval"] is True
        assert status["missing"] == []

    def test_identity_provider_is_swappable(self, tmp_path, repo):
        other = identity.HumanIdentity(name="Grace Hopper", email="grace@example.com")
        server = make_server(
            tmp_path, repo, identity_provider=StaticIdentityProvider(other)
        )
        result = call(
            server, "gate.approve", {"subject": "main", "commit": head(repo)}
        )["result"]
        assert result["approver"] == {"name": other.name, "email": other.email}

    def test_missing_identity_refuses_never_anonymous(self, tmp_path, repo):
        git(repo, "config", "user.name", "")
        git(repo, "config", "user.email", "")
        server = make_server(tmp_path, repo)
        response = call(
            server, "gate.approve", {"subject": "main", "commit": head(repo)}
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "identity" in response["error"]["message"]
        # Nothing was recorded: an anonymous approval must not exist.
        assert server.ledger.query(action_type="approval") == []

    def test_missing_subject_or_commit_is_invalid_params(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        for params in ({"commit": "a"}, {"subject": "main"}):
            response = call(server, "gate.approve", params)
            assert response["error"]["code"] == protocol.INVALID_PARAMS, params


class TestGateStatusRpc:
    def test_blocked_status_carries_missing_report(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        result = call(
            server, "gate.status", {"subject": "main", "commit": head(repo)}
        )["result"]
        assert result["status"] == "blocked"
        assert result["requiredApproval"] is True
        assert any("no recorded human approval" in m for m in result["missing"])
        assert "approvalSequence" not in result

    def test_stale_approval_reports_invalidated_binding(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        old_head = head(repo)
        seq = call(
            server, "gate.approve", {"subject": "main", "commit": old_head}
        )["result"]["sequence"]
        result = call(
            server, "gate.status", {"subject": "main", "commit": "f" * 40}
        )["result"]
        assert result["status"] == "blocked"
        assert any("invalidated" in m for m in result["missing"])
        assert "approvalSequence" not in result
        # The stale approval row is still in the ledger — facts are kept.
        assert server.ledger.get_entry(seq)["decision"] == "approved"

    def test_halted_merge_reports_halted(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        append_halt(server.ledger, "incident: freeze", subject="main")
        result = call(
            server, "gate.status", {"subject": "main", "commit": head(repo)}
        )["result"]
        assert result["status"] == "blocked"
        assert result["halted"] is True
        assert any("freeze" in m for m in result["missing"])

    def test_unprotected_branch_status(self, tmp_path, repo):
        server = make_server(tmp_path, repo)
        result = call(
            server,
            "gate.status",
            {"subject": "feature/story-1", "commit": head(repo)},
        )["result"]
        assert result["status"] == "approved"
        assert result["requiredApproval"] is False

    def test_governor_disabled_refuses_and_touches_nothing(self, tmp_path, repo):
        server = SidecarServer()
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "workspaceDir": str(repo),
                },
            }
        )
        for method, params in (
            ("gate.approve", {"subject": "main", "commit": "a" * 40}),
            ("gate.status", {"subject": "main", "commit": "a" * 40}),
        ):
            response = call(server, method, params)
            assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED, method
        assert not (repo / ".meridian" / "ledger").exists()
