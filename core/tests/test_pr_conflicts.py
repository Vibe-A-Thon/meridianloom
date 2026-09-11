"""Multi-agent conflict detection (FR-M35-07; F1 Workstream B task 13).

Two agents touching the same story: every hunk is attributed to its agent
(trailers first, author markers next, human authors direct), and
agent-vs-agent conflicts are surfaced as a DISTINCT rework class —
agent-conflict — recorded in the ledger before the RPC returns
(FR-M10-08), idempotently. Same-agent rework is never a conflict.

Fixtures are real git repositories: commit A authored by the Copilot agent
(author mailbox marker), commit B by the Claude agent (Co-Authored-By
trailer) whose hunk edits the lines A wrote — an overlapping edit; and a
control range where the two agents touch disjoint files — no conflicts.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.pr import conflicts as pr_conflicts
from meridian_core.server import SidecarServer

PACK_TEXT = """
version: 2
protectedBranches: [main]
profiles: {}
"""

CLAUDE_ENV = {
    "GIT_AUTHOR_NAME": "Dev User",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Dev User",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
}

COPILOT_ENV = {
    "GIT_AUTHOR_NAME": "copilot-swe-agent",
    "GIT_AUTHOR_EMAIL": "19872456+copilot-swe-agent@users.noreply.github.com",
    "GIT_COMMITTER_NAME": "copilot-swe-agent",
    "GIT_COMMITTER_EMAIL": "19872456+copilot-swe-agent@users.noreply.github.com",
}


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
            "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.com",
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
    """main with app.txt (12 lines); the agents' commits land on 'work'."""
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init")
    lines = [f"line {i}" for i in range(1, 13)]
    (target / "app.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (target / "other.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    git(target, "add", ".")
    git(target, "commit", "-m", "initial")
    git(target, "checkout", "-b", "work")
    return target


def commit_copilot_edit(repo: Path) -> str:
    """Agent A (Copilot, author-mailbox marker) edits lines 5-6 of app.txt."""
    lines = (repo / "app.txt").read_text(encoding="utf-8").splitlines()
    lines[4] = "line 5 rewritten by copilot"
    lines[5] = "line 6 rewritten by copilot"
    (repo / "app.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "copilot: rewrite lines 5-6", env_extra=COPILOT_ENV)
    return git(repo, "rev-parse", "HEAD").strip()


def commit_claude_overlap(repo: Path) -> str:
    """Agent B (Claude, Co-Authored-By trailer) edits line 6 — the line A
    wrote — plus line 7: an overlapping edit over agent A's lines."""
    lines = (repo / "app.txt").read_text(encoding="utf-8").splitlines()
    lines[5] = "line 6 reworked by claude over copilot's line"
    lines[6] = "line 7 extended by claude"
    (repo / "app.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    git(repo, "add", ".")
    git(
        repo,
        "commit",
        "-m",
        "claude: rework line 6\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        env_extra=CLAUDE_ENV,
    )
    return git(repo, "rev-parse", "HEAD").strip()


def commit_claude_disjoint(repo: Path) -> str:
    """Agent B touches only other.txt — no overlap with A's app.txt edit."""
    (repo / "other.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    git(repo, "add", ".")
    git(
        repo,
        "commit",
        "-m",
        "claude: extend other.txt\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        env_extra=CLAUDE_ENV,
    )
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture()
def server(tmp_path: Path) -> SidecarServer:
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
    instance.handle_message(
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
    return instance


def call(server: SidecarServer, method: str, params: dict, request_id: int = 99) -> dict:
    return server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


class TestCommitAttribution:
    def test_trailer_beats_author(self, repo: Path):
        sha = commit_claude_overlap(repo)
        agent = pr_conflicts.attribution_for_commit(repo, sha)
        assert agent.vendor == "claude"
        assert agent.source == "trailer"
        assert agent.confidence == "telemetry"

    def test_author_name_marker(self, repo: Path):
        sha = commit_copilot_edit(repo)
        agent = pr_conflicts.attribution_for_commit(repo, sha)
        assert agent.vendor == "github-copilot"
        assert agent.source == "name-marker"

    def test_human_author_is_direct(self, repo: Path):
        sha = git(repo, "rev-parse", "main").strip()
        agent = pr_conflicts.attribution_for_commit(repo, sha)
        assert agent.vendor == "human"
        assert agent.confidence == "direct"


class TestConflictDetection:
    def test_overlapping_edit_between_two_agents(self, repo: Path):
        a_sha = commit_copilot_edit(repo)
        b_sha = commit_claude_overlap(repo)
        hunks = pr_conflicts.collect_agent_hunks(repo, base="main", ref="HEAD")
        vendors = {h.agent.vendor for h in hunks}
        assert vendors == {"github-copilot", "claude"}

        conflicts = pr_conflicts.detect_conflicts(hunks)
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict.path == "app.txt"
        assert conflict.kind == "edited-over-agent-lines"
        assert conflict.earlier.commit == a_sha
        assert conflict.later.commit == b_sha
        assert conflict.earlier.agent.vendor == "github-copilot"
        assert conflict.later.agent.vendor == "claude"

    def test_disjoint_agent_work_is_not_a_conflict(self, repo: Path):
        commit_copilot_edit(repo)
        commit_claude_disjoint(repo)
        hunks = pr_conflicts.collect_agent_hunks(repo, base="main", ref="HEAD")
        assert pr_conflicts.detect_conflicts(hunks) == []

    def test_same_agent_rework_is_not_a_conflict(self, repo: Path):
        commit_copilot_edit(repo)
        lines = (repo / "app.txt").read_text(encoding="utf-8").splitlines()
        lines[4] = "line 5 again by copilot"
        (repo / "app.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "copilot: rework own lines", env_extra=COPILOT_ENV)
        hunks = pr_conflicts.collect_agent_hunks(repo, base="main", ref="HEAD")
        assert pr_conflicts.detect_conflicts(hunks) == []


@pytest.mark.slow
class TestPrConflictsRpc:
    def test_conflicts_detected_attributed_classified_recorded(
        self, server: SidecarServer, repo: Path, tmp_path: Path
    ):
        pack = tmp_path / "governance.yaml"
        pack.write_text(PACK_TEXT, encoding="utf-8")
        commit_copilot_edit(repo)
        commit_claude_overlap(repo)

        response = call(
            server,
            "pr/conflicts",
            {
                "repoPath": str(repo),
                "base": "main",
                "ref": "HEAD",
                "storyId": "PROJ-77",
                "policyPath": str(pack),
            },
        )
        assert "result" in response, response
        result = response["result"]
        assert result["recorded"] == 1
        assert result["duplicatesSkipped"] == 0

        # Per-hunk agent attribution is returned for the whole range.
        vendors = {h["agent"]["vendor"] for h in result["hunks"]}
        assert vendors == {"github-copilot", "claude"}

        conflict = result["conflicts"][0]
        assert conflict["path"] == "app.txt"
        assert conflict["kind"] == "edited-over-agent-lines"
        assert conflict["agents"][0]["vendor"] == "github-copilot"
        assert conflict["agents"][1]["vendor"] == "claude"
        assert conflict["alreadyRecorded"] is False

        # FR-M10-08: the conflict is in the ledger before the RPC returned.
        row = server.ledger.get_entry(conflict["recordedSequence"])
        assert row is not None
        assert row["action_type"] == "rejection"
        assert row["decision"] == "rejected"
        assert row["rework_reason"] == "agent-conflict"
        assert row["story_id"] == "PROJ-77"
        detail = json.loads(server.ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode("utf-8"))
        assert detail["class"] == "agent-conflict"
        assert row["rejected_commit"] == conflict["earlier"]["commit"]
        assert row["rejecting_commit"] == conflict["later"]["commit"]

    def test_rerun_is_idempotent(self, server: SidecarServer, repo: Path, tmp_path: Path):
        pack = tmp_path / "governance.yaml"
        pack.write_text(PACK_TEXT, encoding="utf-8")
        commit_copilot_edit(repo)
        commit_claude_overlap(repo)
        params = {
            "repoPath": str(repo),
            "base": "main",
            "ref": "HEAD",
            "storyId": "PROJ-77",
            "policyPath": str(pack),
        }
        first = call(server, "pr/conflicts", params)["result"]
        second = call(server, "pr/conflicts", params)["result"]
        assert second["recorded"] == 0
        assert second["duplicatesSkipped"] == 1
        assert second["conflicts"][0]["recordedSequence"] == first["conflicts"][0]["recordedSequence"]
        rows = server.ledger.query(action_type="rejection", limit=1000)
        assert len(rows) == 1

    def test_disjoint_range_records_nothing(
        self, server: SidecarServer, repo: Path, tmp_path: Path
    ):
        pack = tmp_path / "governance.yaml"
        pack.write_text(PACK_TEXT, encoding="utf-8")
        commit_copilot_edit(repo)
        commit_claude_disjoint(repo)
        result = call(
            server,
            "pr/conflicts",
            {
                "repoPath": str(repo),
                "base": "main",
                "ref": "HEAD",
                "policyPath": str(pack),
            },
        )["result"]
        assert result["conflicts"] == []
        assert result["recorded"] == 0
        assert server.ledger.query(action_type="rejection", limit=10) == []

    def test_governor_disabled_refuses(self, tmp_path: Path, repo: Path):
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
        refused = call(
            server, "pr/conflicts", {"repoPath": str(repo), "base": "main", "ref": "HEAD"}
        )
        assert refused["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert ledger.query(limit=10) == []
