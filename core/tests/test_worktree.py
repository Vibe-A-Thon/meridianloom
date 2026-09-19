"""Worktree isolation for hosted agents (FR-M18-01..08; F1 Workstream A task 5).

Every test builds real git repositories in tmp dirs with pinned identity and
timestamps (the established fixture pattern; core.autocrlf is disabled so
line endings never rewrite content on Windows). AC-13 and AC-14 are covered
by name: conflict surfacing before a packet starts, and the primary working
tree left byte-identical across a story abort (tracked-file checksums).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from meridian_core import protocol
from meridian_core import trailers as trailers_mod
from meridian_core.ledger.core import Ledger
from meridian_core.ledger.keys import EphemeralSigningKeyProvider
from meridian_core.server import SidecarServer
from meridian_core.worktree import manager as wt

from test_attribution import ALICE, BOB, T0, git


# -- helpers -----------------------------------------------------------------


def tracked_checksum(repo: Path) -> str:
    """AC-14: one digest over the primary tree's tracked files + the file
    list, so both content changes and add/remove are caught."""
    files = sorted(git(repo, "ls-files").splitlines())
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode("utf-8") + b"\0")
        digest.update((repo / name).read_bytes() + b"\0")
    return digest.hexdigest()


def commit_file(repo: Path, rel: str, content: str, message: str, date: int = T0 + 600):
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    git(repo, "add", rel)
    git(repo, "commit", "-m", message, author=BOB, date=date)
    return git(repo, "rev-parse", "HEAD").strip()


def agent_git(worktree: Path, *args: str) -> str:
    """git in the story worktree with NO pinned identity env: the commit
    must pick the worktree-local agent config up, like a real hosted agent
    process (which the host does not litter with GIT_AUTHOR_* variables)."""
    result = subprocess.run(
        [
            "git",
            "-c", "core.quotepath=false",
            "-c", "core.autocrlf=false",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
    return result.stdout


def agent_commit(worktree: Path, rel: str, content: str, message: str):
    """What a hosted agent does: plain file writes + git, nothing else."""
    target = worktree / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    agent_git(worktree, "add", rel)
    agent_git(worktree, "commit", "-m", message)
    return agent_git(worktree, "rev-parse", "HEAD").strip()


def manager(repo: Path) -> wt.WorktreeManager:
    return wt.WorktreeManager(repo)


def last_commit_message(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%B")


# -- FR-M18-01/02: creation ---------------------------------------------------


class TestWorktreeCreate:
    def test_creates_worktree_under_meridian_dir_on_story_branch(self, repo):
        info = manager(repo).create("story-1", "gemini")
        assert info.story_id == "story-1"
        assert info.branch == "meridian/story-1"
        assert info.path == repo / ".meridian" / "worktrees" / "story-1"
        assert info.path.is_dir()
        assert info.worktree_ref == ".meridian/worktrees/story-1"
        # The branch exists and sits on the base commit.
        assert git(repo, "rev-parse", info.branch).strip() == info.base_commit
        assert info.base_branch == "main"
        assert info.head_commit == info.base_commit
        assert info.dirty is False  # nothing Meridian owns lives in the tree

    def test_primary_tree_is_never_the_write_target(self, repo):
        before = tracked_checksum(repo)
        tracked_before = git(repo, "status", "--porcelain", "--untracked-files=no")
        manager(repo).create("story-1", "gemini")
        # No tracked file changed (the worktree dir itself lives under
        # .meridian/, Meridian's own scratch space — untracked, like the
        # ledger, and invisible to tracked-file integrity).
        assert tracked_checksum(repo) == before
        assert (
            git(repo, "status", "--porcelain", "--untracked-files=no")
            == tracked_before
            == ""
        )

    def test_base_branch_is_configurable(self, repo):
        git(repo, "branch", "develop")
        info = manager(repo).create("story-2", "gemini", base_branch="develop")
        assert info.base_branch == "develop"
        assert info.base_commit == git(repo, "rev-parse", "develop").strip()

    def test_missing_base_branch_is_actionable(self, repo):
        with pytest.raises(wt.WorktreeError, match="base branch 'nope'"):
            manager(repo).create("story-1", "gemini", base_branch="nope")

    def test_create_twice_refuses(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        with pytest.raises(wt.WorktreeExistsError):
            mgr.create("story-1", "gemini")

    def test_story_id_cannot_escape_the_worktrees_dir(self, repo):
        with pytest.raises(wt.WorktreeError, match="storyId"):
            manager(repo).create("../evil", "gemini")
        with pytest.raises(wt.WorktreeError, match="adapterId"):
            manager(repo).create("story-1", "bad id; rm -rf /")
        assert not (repo / "evil").exists()

    def test_create_is_resumable_when_the_branch_already_exists(self, repo):
        git(repo, "branch", "meridian/story-1")
        info = manager(repo).create("story-1", "gemini")
        assert info.branch == "meridian/story-1"
        assert info.head_commit == git(repo, "rev-parse", "main").strip()


# -- FR-M18-05/07: identity + trailer ------------------------------------------


class TestAgentIdentityAndTrailer:
    def test_identity_is_deterministic_and_adapter_derived(self):
        assert wt.agent_identity("gemini") == wt.agent_identity("gemini")
        name, email = wt.agent_identity("gemini")
        assert name == "Meridian Agent (gemini)"
        assert email == "gemini@agents.meridian.local"
        assert wt.agent_identity("gemini") != wt.agent_identity("claude-code")

    def test_worktree_local_config_carries_agent_identity(self, repo):
        path = manager(repo).create("story-1", "gemini").path
        assert git(path, "config", "--worktree", "user.name").strip() == (
            "Meridian Agent (gemini)"
        )
        assert git(path, "config", "--worktree", "user.email").strip() == (
            "gemini@agents.meridian.local"
        )
        # Repo-local (human) identity is untouched — blame can tell them apart.
        assert git(repo, "config", "user.name").strip() != "Meridian Agent (gemini)"

    def test_every_agent_commit_carries_identity_and_trailer(self, repo):
        path = manager(repo).create("story-1", "gemini").path
        agent_commit(path, "src/feature.txt", "agent work\n", "feat: agent work")
        assert git(path, "log", "-1", "--format=%an <%ae>").strip() == (
            "Meridian Agent (gemini) <gemini@agents.meridian.local>"
        )
        # AC-21 shape: the trailer is readable from the commit message with
        # the standard trailer parser (has_trailer scans the whole message;
        # the subject line of a one-line message is trailer-shaped too).
        message = last_commit_message(path)
        assert trailers_mod.has_trailer(message, wt.TRAILER_KEY)
        assert (wt.TRAILER_KEY, "gemini") in trailers_mod.parse_trailers(message)
        assert git(
            path,
            "log",
            "-1",
            "--format=%(trailers:key=" + wt.TRAILER_KEY + ",valueonly=true)",
        ).strip() == "gemini"

    def test_trailer_appends_to_every_commit_not_just_the_first(self, repo):
        path = manager(repo).create("story-1", "gemini").path
        agent_commit(path, "a.txt", "one\n", "feat: one")
        agent_commit(path, "b.txt", "two\n", "feat: two")
        trailers = git(
            path,
            "log",
            "--format=%(trailers:key=" + wt.TRAILER_KEY + ",valueonly=true)",
            "-2",
        ).split()
        assert trailers == ["gemini", "gemini"]

    def test_primary_tree_commits_do_not_get_the_agent_trailer(self, repo):
        manager(repo).create("story-1", "gemini")
        commit_file(repo, "human.txt", "human work\n", "docs: human work")
        assert not trailers_mod.has_trailer(
            last_commit_message(repo), wt.TRAILER_KEY
        )

    def test_blame_attributes_agent_lines_to_the_agent(self, repo):
        path = manager(repo).create("story-1", "gemini").path
        agent_commit(path, "src/app.txt", "agent line\n", "feat: agent line")
        blame = git(
            path, "blame", "--line-porcelain", "src/app.txt"
        ).splitlines()
        authors = [line for line in blame if line.startswith("author ")]
        assert authors == ["author Meridian Agent (gemini)"]
        author_mails = [
            line for line in blame if line.startswith("author-mail ")
        ]
        assert author_mails == ["author-mail <gemini@agents.meridian.local>"]


# -- list / remove ------------------------------------------------------------


@pytest.mark.slow
class TestListAndRemove:
    def test_list_only_meridian_worktrees(self, repo):
        mgr = manager(repo)
        assert mgr.list() == []
        mgr.create("story-2", "gemini")
        mgr.create("story-1", "claude-code")
        infos = mgr.list()
        assert [info.story_id for info in infos] == ["story-1", "story-2"]
        assert all(info.adapter_id for info in infos)

    def test_remove_refuses_dirty_worktree(self, repo):
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        (path / "uncommitted.txt").write_text("precious\n", encoding="utf-8")
        with pytest.raises(wt.WorktreeDirtyError) as excinfo:
            mgr.remove("story-1")
        assert "uncommitted.txt" in str(excinfo.value)
        # Refusal is side-effect free: the worktree (and its content) stays.
        assert (path / "uncommitted.txt").exists()
        assert mgr.exists("story-1")

    def test_remove_force_reclaims_dirty_worktree_but_keeps_branch(self, repo):
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        (path / "scratch.txt").write_text("scratch\n", encoding="utf-8")
        info = mgr.remove("story-1", force=True)
        assert not path.exists()
        assert git(repo, "rev-parse", "--verify", info.branch).strip()

    def test_remove_unknown_story_is_actionable(self, repo):
        with pytest.raises(wt.WorktreeNotFoundError, match="story-9"):
            manager(repo).remove("story-9")


# -- FR-M18-04 / AC-14: story abort --------------------------------------------


@pytest.mark.slow
class TestStoryAbort:
    def test_ac14_abort_leaves_primary_tree_byte_identical(self, repo):
        mgr = manager(repo)
        before = tracked_checksum(repo)
        path = mgr.create("story-1", "gemini").path
        # The hosted agent works: files, commits, even a new directory.
        agent_commit(path, "src/app.txt", "one\ntwo\nthree\nagent\n", "feat: grow")
        agent_commit(path, "src/new/module.txt", "new file\n", "feat: module")
        assert tracked_checksum(repo) == before  # nothing written to primary
        info, branch_deleted, kept = mgr.abort("story-1")
        assert info.story_id == "story-1"
        assert branch_deleted is True
        assert kept is None
        # The worktree is gone, the never-pushed branch is gone, and the
        # primary working tree is byte-identical to its pre-story state.
        assert not path.exists()
        assert not (repo / ".meridian" / "worktrees" / "story-1").exists()
        assert tracked_checksum(repo) == before
        # Tracked state untouched (the .meridian/ scratch dir is Meridian's
        # own, like the ledger; what AC-14 promises is the tracked tree).
        assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
        assert git(repo, "for-each-ref", "refs/heads/meridian").strip() == ""

    def test_abort_discards_unmerged_agent_commits_with_the_branch(self, repo):
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        agent_commit(path, "src/app.txt", "agent\n", "feat: agent change")
        head = git(path, "rev-parse", "HEAD").strip()
        mgr.abort("story-1")
        # The unpushed agent commit vanished with the branch — recoverable
        # nowhere, which is exactly what an abort means.
        refs = git(repo, "for-each-ref", "refs/heads").splitlines()
        assert not any("meridian/story-1" in ref for ref in refs)

    def test_abort_keeps_a_pushed_branch_for_the_record(self, repo):
        origin = repo.parent / "origin.git"
        git(repo.parent, "init", "--bare", str(origin))
        git(repo, "remote", "add", "origin", str(origin))
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        agent_commit(path, "src/app.txt", "agent\n", "feat: agent change")
        git(path, "push", "-u", "origin", "meridian/story-1")
        _, branch_deleted, kept = mgr.abort("story-1")
        assert branch_deleted is False
        assert kept is not None and "origin" in kept
        assert git(repo, "rev-parse", "--verify", "meridian/story-1").strip()

    def test_abort_unknown_story_is_actionable(self, repo):
        with pytest.raises(wt.WorktreeNotFoundError, match="story-9"):
            manager(repo).abort("story-9")


# -- FR-M18-03 / AC-13: pre-flight conflict detection ---------------------------


@pytest.mark.slow
class TestConflicts:
    def test_clean_tree_has_no_conflicts(self, repo):
        report = manager(repo).conflicts(story_id="story-1")
        assert report.blocked is False
        assert report.conflicts == ()

    def test_ac13_uncommitted_human_edit_to_target_blocks_start(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        # The human edits a file in the PRIMARY tree, uncommitted.
        (repo / "src" / "app.txt").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        report = mgr.conflicts(
            story_id="story-1", target_paths=["src/app.txt"]
        )
        assert report.blocked is True
        kinds = [c.kind for c in report.conflicts]
        assert "primary_uncommitted" in kinds
        hit = next(c for c in report.conflicts if c.kind == "primary_uncommitted")
        assert hit.path == "src/app.txt"

    def test_packet_targets_a_different_file_than_the_human_edit(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        (repo / "README.md").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        report = mgr.conflicts(
            story_id="story-1", target_paths=["src/app.txt"]
        )
        assert report.blocked is False

    def test_without_target_paths_every_dirty_file_blocks(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        (repo / "README.md").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        report = manager(repo).conflicts(story_id="story-1")
        assert report.blocked is True
        assert [c.path for c in report.conflicts] == ["README.md"]

    def test_untracked_human_file_matching_target_blocks(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        (repo / "src" / "planned.txt").write_text(
            "human sketch\n", encoding="utf-8", newline="\n"
        )
        report = mgr.conflicts(
            story_id="story-1", target_paths=["src/planned.txt"]
        )
        assert report.blocked is True
        assert report.conflicts[0].kind == "primary_uncommitted"

    def test_unmerged_upstream_changes_block(self, repo):
        mgr = manager(repo)
        mgr.create("story-1", "gemini")
        # The human lands a commit on main after the story branch forked.
        commit_file(repo, "README.md", "upstream moved\n", "docs: upstream")
        report = manager(repo).conflicts(story_id="story-1")
        assert report.blocked is True
        upstream = next(
            c for c in report.conflicts if c.kind == "unmerged_upstream"
        )
        assert "1 commit(s) not on story branch" in upstream.detail
        assert upstream.path is None

    def test_worktree_uncommitted_state_blocks(self, repo):
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        (path / "wip.txt").write_text("agent wip\n", encoding="utf-8")
        report = manager(repo).conflicts(story_id="story-1")
        assert report.blocked is True
        kinds = [c.kind for c in report.conflicts]
        assert "worktree_uncommitted" in kinds

    def test_worktree_unpushed_commits_block(self, repo):
        mgr = manager(repo)
        path = mgr.create("story-1", "gemini").path
        agent_commit(path, "src/app.txt", "agent\n", "feat: agent change")
        report = manager(repo).conflicts(story_id="story-1")
        assert report.blocked is True
        unpushed = next(
            c for c in report.conflicts if c.kind == "worktree_unpushed"
        )
        assert "1 commit(s)" in unpushed.detail
        # A clean re-run is not blocked: abort removes the worktree AND the
        # unpushed branch, so a fresh create starts from the base commit.
        mgr.abort("story-1")
        mgr.create("story-1", "gemini")
        assert manager(repo).conflicts(story_id="story-1").blocked is False

    def test_without_story_only_primary_checks_run(self, repo):
        (repo / "README.md").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        report = manager(repo).conflicts()
        assert report.blocked is True
        assert [c.kind for c in report.conflicts] == ["primary_uncommitted"]


# -- RPC surface: tier gate + ledger linkage -----------------------------------


@pytest.fixture()
def server(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    instance = SidecarServer(ledger=ledger)
    yield instance
    ledger.close()


@pytest.fixture()
def governed_server(repo):
    """A governor-enabled server whose ledger lives OUTSIDE the repository.

    (The pytest tmp_path is shared across a test's fixtures, and the repo
    fixture `git add .`-tracks everything present — a ledger inside the repo
    would become a tracked file and pollute tracked-tree assertions. The
    per-test name keeps one session's ledgers from colliding too.)"""
    ledger = Ledger(
        repo.parent / f"{repo.name}-ledger", EphemeralSigningKeyProvider()
    )
    instance = SidecarServer(ledger=ledger)
    enable_governor(instance)
    yield instance
    ledger.close()


def call(server: SidecarServer, request_id: int, method: str, params: dict) -> dict:
    response = server.handle_message(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    assert response is not None and response["id"] == request_id
    return response


def result(server, method, params=None):
    response = call(server, 7, method, params or {})
    assert "error" not in response, response.get("error")
    return response["result"]


def enable_governor(server: SidecarServer) -> None:
    server.handle_message(
        {
            "jsonrpc": "2.0",
            "method": "tiers/set",
            "params": {"tiers": ["flight-recorder", "governor"]},
        }
    )


class TestRpcTierGate:
    METHODS = [
        ("worktree/create", {"storyId": "s", "adapterId": "gemini"}),
        ("worktree/list", {}),
        ("worktree/remove", {"storyId": "s"}),
        ("worktree/abortStory", {"storyId": "s"}),
        ("worktree/conflicts", {}),
    ]

    @pytest.mark.parametrize("method,params", METHODS)
    def test_governor_disabled_refuses_worktree_methods(self, server, method, params):
        response = call(server, 1, method, dict(params, repoPath="/tmp/x"))
        assert response["error"]["code"] == protocol.ERROR_TIER_DISABLED
        assert response["error"]["data"]["tier"] == "governor"
        assert response["error"]["data"]["capability"] == "governor.worktrees"

    def test_governor_enabled_unlocks_them(self, server, repo):
        enable_governor(server)
        created = result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", "repoPath": str(repo)},
        )
        assert created["worktree"]["branch"] == "meridian/story-1"


@pytest.mark.slow
class TestWorktreeRpc:
    def test_create_result_shape_and_ledger_entry(self, governed_server, repo):
        server = governed_server
        created = result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", "repoPath": str(repo)},
        )
        info = created["worktree"]
        assert info == {
            "storyId": "story-1",
            "branch": "meridian/story-1",
            "path": str(repo / ".meridian" / "worktrees" / "story-1"),
            "worktreeRef": ".meridian/worktrees/story-1",
            "baseBranch": "main",
            "baseCommit": git(repo, "rev-parse", "main").strip(),
            "headCommit": git(repo, "rev-parse", "main").strip(),
            "adapterId": "gemini",
            "dirty": False,
            "unpushedCommits": 0,
        }
        # Task 5f: creation is ledger-recorded with worktree_ref set.
        entries = result(server, "ledger.query", {"actionType": "worktree_create"})[
            "entries"
        ]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["worktreeRef"] == ".meridian/worktrees/story-1"
        assert entry["storyId"] == "story-1"
        assert entry["actorId"] == "gemini"
        detail = json.loads(
            result(server, "ledger.getEntry", {"sequence": entry["sequence"]})["input"]
        )
        assert detail["identity"] == [
            "Meridian Agent (gemini)",
            "gemini@agents.meridian.local",
        ]
        assert detail["trailer"] == wt.TRAILER_KEY

    def test_list_reports_created_worktrees(self, governed_server, repo):
        server = governed_server
        params = {"storyId": "story-1", "adapterId": "gemini", "repoPath": str(repo)}
        result(server, "worktree/create", params)
        listed = result(server, "worktree/list", {"repoPath": str(repo)})
        assert [w["storyId"] for w in listed["worktrees"]] == ["story-1"]

    def test_remove_is_ledger_recorded_and_branch_survives(self, governed_server, repo):
        server = governed_server
        base = {"repoPath": str(repo)}
        result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", **base},
        )
        removed = result(server, "worktree/remove", {"storyId": "story-1", **base})
        assert removed["removed"] is True
        assert removed["branch"] == "meridian/story-1"
        assert git(repo, "rev-parse", "--verify", "meridian/story-1").strip()
        entries = result(server, "ledger.query", {"actionType": "worktree_remove"})[
            "entries"
        ]
        assert len(entries) == 1
        assert entries[0]["worktreeRef"] == ".meridian/worktrees/story-1"

    def test_abort_story_is_ledger_recorded(self, governed_server, repo):
        server = governed_server
        base = {"repoPath": str(repo)}
        result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", **base},
        )
        aborted = result(server, "worktree/abortStory", {"storyId": "story-1", **base})
        assert aborted["branchDeleted"] is True
        assert "branchKeptReason" not in aborted
        entries = result(server, "ledger.query", {"actionType": "story_abort"})[
            "entries"
        ]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["worktreeRef"] == ".meridian/worktrees/story-1"
        assert entry["actorId"] == "human"  # FR-M18-04: a human act, recorded
        assert git(repo, "for-each-ref", "refs/heads/meridian").strip() == ""

    def test_conflicts_rpc_returns_the_structured_report(self, governed_server, repo):
        server = governed_server
        base = {"repoPath": str(repo)}
        result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", **base},
        )
        (repo / "src" / "app.txt").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        report = result(
            server,
            "worktree/conflicts",
            {"storyId": "story-1", "targetPaths": ["src/app.txt"], **base},
        )
        assert report["blocked"] is True
        assert report["baseBranch"] == "main"
        assert report["repoPath"] == str(manager(repo).repo)
        kinds = [c["kind"] for c in report["conflicts"]]
        assert "primary_uncommitted" in kinds

    def test_ac13_and_ac14_end_to_end_over_the_bus(self, governed_server, repo):
        """The acceptance shapes over the RPC surface: a human edit blocks the
        packet start (AC-13); after an abort the primary tree checksum is
        unchanged (AC-14)."""
        server = governed_server
        base = {"repoPath": str(repo)}
        before = tracked_checksum(repo)
        result(
            server,
            "worktree/create",
            {"storyId": "story-1", "adapterId": "gemini", **base},
        )
        wt_path = repo / ".meridian" / "worktrees" / "story-1"
        agent_commit(wt_path, "src/app.txt", "agent\n", "feat: agent change")
        (repo / "src" / "app.txt").write_text(
            "human edit\n", encoding="utf-8", newline="\n"
        )
        blocked = result(
            server,
            "worktree/conflicts",
            {"storyId": "story-1", "targetPaths": ["src/app.txt"], **base},
        )
        assert blocked["blocked"] is True  # AC-13: the edit is never lost
        assert "primary_uncommitted" in [
            c["kind"] for c in blocked["conflicts"]
        ]
        # The human reverts; the primary conflict is gone (the agent's
        # unpushed commit in the worktree is a separate, honest signal).
        git(repo, "checkout", "--", "src/app.txt")
        after_revert = result(
            server,
            "worktree/conflicts",
            {"storyId": "story-1", "targetPaths": ["src/app.txt"], **base},
        )
        assert "primary_uncommitted" not in [
            c["kind"] for c in after_revert["conflicts"]
        ]
        result(server, "worktree/abortStory", {"storyId": "story-1", **base})
        assert tracked_checksum(repo) == before  # AC-14

    def test_missing_repo_is_actionable(self, server):
        enable_governor(server)
        response = call(server, 1, "worktree/list", {})
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "repoPath" in response["error"]["message"]
