"""Diff and blame engine (F0 Workstream C task 13).

Fixture repositories are created in tmp dirs with pinned author/committer
identity and timestamps so every assertion is deterministic (Windows-robust:
core.autocrlf is disabled in fixtures so line endings never rewrite content).

FR-M33-02 subset (git-native structural attribution): every changed line is
mapped to (commit, author identity, timestamp, line content) — blame for
committed state, diff for uncommitted/unstaged changes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from meridian_core.attribution import blame, diff as attribution_diff

T0 = 1_700_000_000  # fixed epoch base; each commit bumps by 10 minutes

ALICE = ("Alice A", "alice@example.com")
BOB = ("Bob B", "bob@example.com")
CAROL = ("Carol C", "carol@example.com")


def git(repo: Path, *args: str, author: tuple[str, str] = ALICE, date: int = T0) -> str:
    """Run git deterministically in a fixture repo.

    Identity and dates are pinned per commit; CRLF conversion, GPG and
    default-branch surprises are all disabled.
    """
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = author[0]
    env["GIT_AUTHOR_EMAIL"] = author[1]
    env["GIT_AUTHOR_DATE"] = f"{date} +0000"
    env["GIT_COMMITTER_NAME"] = author[0]
    env["GIT_COMMITTER_EMAIL"] = author[1]
    env["GIT_COMMITTER_DATE"] = f"{date} +0000"
    result = subprocess.run(
        [
            "git",
            "-c", "user.name=" + author[0],
            "-c", "user.email=" + author[1],
            "-c", "core.autocrlf=false",
            "-c", "commit.gpgsign=false",
            "-c", "init.defaultBranch=main",
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
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path


class TestBlame:
    def test_every_line_mapped_to_commit_author_time_and_content(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "add four", author=BOB, date=T0 + 600)

        lines = blame.blame(repo, ref="HEAD", paths=["src/app.txt"])

        assert [line.line for line in lines] == [1, 2, 3, 4]
        assert all(line.path == "src/app.txt" for line in lines)
        # The first three lines belong to the initial commit by Alice.
        for line in lines[:3]:
            assert line.content in {"one", "two", "three"}
            assert line.author_name == "Alice A"
            assert line.author_email == "alice@example.com"
            assert line.author_time == "2023-11-14T22:13:20+00:00"
        # The fourth line is Bob's, one commit later.
        assert lines[3].content == "four"
        assert lines[3].author_name == "Bob B"
        assert lines[3].author_time == "2023-11-14T22:23:20+00:00"
        assert lines[0].commit != lines[3].commit
        assert len(lines[0].commit) == 40  # full hex sha

    def test_ref_selects_historical_state(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "add four", author=BOB, date=T0 + 600)

        lines = blame.blame(repo, ref="HEAD~1", paths=["src/app.txt"])

        assert [line.content for line in lines] == ["one", "two", "three"]
        assert all(line.author_name == "Alice A" for line in lines)

    def test_worktree_relative_path_filter(self, repo):
        (repo / "src" / "nested.txt").write_text("nested\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "nested", date=T0 + 600)

        lines = blame.blame(repo, paths=["src/nested.txt"])

        assert len(lines) == 1
        assert lines[0].path == "src/nested.txt"
        assert lines[0].content == "nested"

    def test_blame_without_paths_covers_tracked_files(self, repo):
        lines = blame.blame(repo)
        paths = {line.path for line in lines}
        assert paths == {"src/app.txt", "README.md"}

    def test_windows_style_paths_accepted(self, repo):
        lines = blame.blame(repo, paths=["src\\app.txt"])
        assert len(lines) == 3

    def test_merge_commit_attributes_lines_to_introducing_commit(self, repo):
        git(repo, "checkout", "-b", "feature")
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfeature line\n", encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "feature work", author=BOB, date=T0 + 600)
        git(repo, "checkout", "main")
        (repo / "README.md").write_text("hello\nmain note\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "main work", author=CAROL, date=T0 + 1200)
        git(repo, "merge", "--no-ff", "-m", "merge feature", "feature", date=T0 + 1800)

        merge_hex = git(repo, "rev-parse", "HEAD").strip()
        lines = blame.blame(repo, paths=["src/app.txt", "README.md"])
        by_content = {line.content: line for line in lines}

        # Blame never lands on the merge commit itself: each line belongs to
        # the branch commit that introduced it.
        assert "feature line" in by_content
        assert by_content["feature line"].author_name == "Bob B"
        assert by_content["feature line"].commit != merge_hex
        assert by_content["main note"].author_name == "Carol C"
        assert all(line.commit != merge_hex for line in lines)

    def test_rename_is_followed(self, repo):
        git(repo, "mv", "README.md", "GUIDE.md")
        git(repo, "commit", "-m", "rename", date=T0 + 600)
        (repo / "GUIDE.md").write_text("hello\nguide\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "extend guide", author=BOB, date=T0 + 1200)

        lines = blame.blame(repo, paths=["GUIDE.md"])

        by_content = {line.content: line for line in lines}
        assert by_content["hello"].author_name == "Alice A"
        assert by_content["guide"].author_name == "Bob B"

    def test_crlf_content_is_reported_without_carriage_return(self, repo):
        (repo / "crlf.txt").write_bytes(b"alpha\r\nbeta\r\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "crlf", date=T0 + 600)

        lines = blame.blame(repo, paths=["crlf.txt"])

        assert [line.content for line in lines] == ["alpha", "beta"]

    def test_not_a_repository_is_a_clean_error(self, tmp_path):
        with pytest.raises(blame.AttributionError, match="not a git repository"):
            blame.blame(tmp_path)

    def test_missing_file_is_a_clean_error(self, repo):
        with pytest.raises(blame.AttributionError, match="no such path"):
            blame.blame(repo, paths=["does/not/exist.txt"])

    def test_path_escape_is_refused(self, repo):
        with pytest.raises(blame.AttributionError, match="inside the repository"):
            blame.blame(repo, paths=["../outside.txt"])


class TestDiff:
    def test_uncommitted_changes_carry_null_commit(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        (repo / "newfile.txt").write_text("brand new\n", encoding="utf-8")
        (repo / "README.md").unlink()

        files = {file.path: file for file in attribution_diff.diff(repo)}

        assert set(files) == {"src/app.txt", "newfile.txt", "README.md"}
        app = files["src/app.txt"]
        assert app.status == "modified"
        added = [line for line in app.hunks[0].lines if line.kind == "added"]
        assert [line.content for line in added] == ["four"]
        assert all(line.commit is None for line in added)
        assert added[0].new_line == 4
        removed = [line for line in app.hunks[0].lines if line.kind == "removed"]
        assert removed == []
        assert files["newfile.txt"].status == "added"
        assert files["README.md"].status == "deleted"

    def test_staged_changes(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nstaged\n", encoding="utf-8"
        )
        git(repo, "add", ".")

        files = attribution_diff.diff(repo, staged=True)

        assert len(files) == 1
        added = [
            line
            for hunk in files[0].hunks
            for line in hunk.lines
            if line.kind == "added"
        ]
        assert [line.content for line in added] == ["staged"]

    def test_range_diff_attributes_added_lines_to_commits(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "four", author=BOB, date=T0 + 600)
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\nfive\n", encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "five", author=CAROL, date=T0 + 1200)

        files = attribution_diff.diff(repo, base="HEAD~2", compare="HEAD")

        assert len(files) == 1
        added = [
            line
            for hunk in files[0].hunks
            for line in hunk.lines
            if line.kind == "added"
        ]
        assert [line.content for line in added] == ["four", "five"]
        assert added[0].author_name == "Bob B"
        assert added[1].author_name == "Carol C"
        assert added[0].author_time == "2023-11-14T22:23:20+00:00"
        assert len(added[0].commit) == 40
        assert added[0].commit != added[1].commit

    def test_removed_lines_keep_old_line_numbers(self, repo):
        (repo / "src" / "app.txt").write_text("one\nthree\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "drop two", date=T0 + 600)

        files = attribution_diff.diff(repo, base="HEAD~1", compare="HEAD")

        removed = [
            line
            for hunk in files[0].hunks
            for line in hunk.lines
            if line.kind == "removed"
        ]
        assert [line.content for line in removed] == ["two"]
        assert removed[0].old_line == 2
        assert removed[0].new_line is None

    def test_rename_detected(self, repo):
        git(repo, "mv", "README.md", "GUIDE.md")
        git(repo, "commit", "-m", "rename", date=T0 + 600)

        files = attribution_diff.diff(repo, base="HEAD~1", compare="HEAD")

        assert len(files) == 1
        assert files[0].status == "renamed"
        assert files[0].path == "GUIDE.md"
        assert files[0].old_path == "README.md"

    def test_path_filter(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        (repo / "README.md").write_text("hello\nagain\n", encoding="utf-8")

        files = attribution_diff.diff(repo, paths=["src/app.txt"])

        assert [file.path for file in files] == ["src/app.txt"]

    def test_crlf_fixture(self, repo):
        (repo / "crlf.txt").write_bytes(b"alpha\r\nbeta\r\n")

        files = attribution_diff.diff(repo)

        added = [
            line
            for hunk in files[0].hunks
            for line in hunk.lines
            if line.kind == "added"
        ]
        assert [line.content for line in added] == ["alpha", "beta"]

    def test_clean_tree_yields_no_files(self, repo):
        assert attribution_diff.diff(repo) == []

    def test_not_a_repository_is_a_clean_error(self, tmp_path):
        with pytest.raises(attribution_diff.AttributionError, match="not a git repository"):
            attribution_diff.diff(tmp_path)


class TestAttribRpc:
    """attrib/blame and attrib/diff over the dispatch layer (FR-M33-02 bus contract)."""

    def _server(self, tmp_path, **handshake_extra):
        from meridian_core import protocol
        from meridian_core.server import SidecarServer

        server = SidecarServer()
        params = {"protocolVersion": protocol.PROTOCOL_VERSION, "client": "pytest"}
        params.update(handshake_extra)
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "handshake", "params": params}
        )
        assert response is not None and "result" in response
        return server

    def _call(self, server, method, params):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 99, "method": method, "params": params}
        )
        assert response is not None
        return response

    def test_blame_round_trip(self, repo):
        server = self._server(repo, workspaceDir=str(repo))
        response = self._call(
            server, "attrib/blame", {"repoPath": str(repo), "paths": ["README.md"]}
        )
        assert "result" in response, response
        result = response["result"]
        assert result["repoPath"].replace("\\", "/").endswith(str(repo).replace("\\", "/").rsplit("/", 1)[-1])
        assert result["ref"] == "HEAD"
        assert [line["content"] for line in result["lines"]] == ["hello"]
        line = result["lines"][0]
        assert line["authorName"] == "Alice A"
        assert line["authorEmail"] == "alice@example.com"
        assert line["authorTime"] == "2023-11-14T22:13:20+00:00"
        assert len(line["commit"]) == 40

    def test_diff_round_trip_marks_worktree_lines_commitless(self, repo):
        (repo / "src" / "app.txt").write_text(
            "one\ntwo\nthree\nfour\n", encoding="utf-8"
        )
        server = self._server(repo, workspaceDir=str(repo))
        response = self._call(server, "attrib/diff", {"repoPath": str(repo)})
        assert "result" in response, response
        files = {f["path"]: f for f in response["result"]["files"]}
        assert files["src/app.txt"]["status"] == "modified"
        added = [
            line
            for h in files["src/app.txt"]["hunks"]
            for line in h["lines"]
            if line["kind"] == "added"
        ]
        assert [line["content"] for line in added] == ["four"]
        assert all(line["commit"] is None for line in added)
        assert response["result"]["staged"] is False

    def test_repo_path_defaults_to_workspace(self, repo):
        server = self._server(repo, workspaceDir=str(repo))
        response = self._call(
            server, "attrib/blame", {"paths": ["README.md"]}
        )
        assert "result" in response, response

    def test_missing_repo_path_is_a_params_error(self, repo):
        from meridian_core import protocol

        server = self._server(repo)  # no workspaceDir in the handshake
        response = self._call(server, "attrib/blame", {})
        assert response["error"]["code"] == protocol.INVALID_PARAMS

    def test_non_repository_is_a_params_error(self, tmp_path):
        from meridian_core import protocol

        server = self._server(tmp_path, workspaceDir=str(tmp_path))
        response = self._call(
            server, "attrib/diff", {"repoPath": str(tmp_path)}
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "not a git repository" in response["error"]["message"]

    def test_owned_by_flight_recorder_capability(self):
        import bus_types

        owning = {
            capability["id"]: capability
            for capability in bus_types.CAPABILITIES
            if "attrib/blame" in capability["rpcMethods"]
            or "attrib/diff" in capability["rpcMethods"]
        }
        assert len(owning) == 1
        (capability,) = owning.values()
        assert capability["tier"] == "flight-recorder"

    def test_methods_listed_in_handshake_capabilities(self, repo):
        from meridian_core import protocol

        server = self._server(repo, workspaceDir=str(repo))
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                },
            }
        )
        methods = response["result"]["capabilities"]["methods"]
        assert "attrib/blame" in methods
        assert "attrib/diff" in methods
