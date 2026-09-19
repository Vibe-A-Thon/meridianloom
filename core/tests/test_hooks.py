"""FR-M36-03 / D23: the opt-in commit-msg provenance trailer hook.

Every test here runs against real git repositories in tmp dirs: install the
hook, record a pending seq range for the staged content, commit, and assert
the ``Meridian-Ledger: <range>`` trailer lands correctly; remove the hook and
assert commits are clean. The trailer mechanics (block awareness, comments,
idempotency, foreign-hook chaining, core.hooksPath) are covered at unit and
end-to-end levels.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from meridian_core import doctor, protocol, trailers
from meridian_core import hooks as provenance_hooks
from meridian_core.attribution._git import AttributionError
from meridian_core.server import SidecarServer


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-pager", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test User")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "commit.gpgsign", "false")
    (root / "file.txt").write_text("one\n", encoding="utf-8")
    git(root, "add", "file.txt")
    git(root, "commit", "-m", "chore: seed")
    return root


def commit(repo: Path, message: str, *extra: str) -> str:
    """Commit the CURRENT index; the message is not written to the worktree."""
    git(repo, "commit", "-m", message, *extra)
    return git(repo, "log", "-1", "--format=%B").strip("\n")


def change_stage_record_commit(
    repo: Path,
    message: str,
    from_seq: int | None = None,
    to_seq: int | None = None,
    *extra: str,
) -> str:
    """The real linkage flow: change a file, stage, record the pending seq
    range for exactly that staged content, then commit — so the tree hash
    the hook recomputes matches the recorded one."""
    (repo / "file.txt").write_text(message + "\n", encoding="utf-8")
    git(repo, "add", "file.txt")
    if from_seq is not None:
        staged_hash = git(repo, "write-tree").strip()
        result = provenance_hooks.record_pending(repo, staged_hash, from_seq, to_seq)
        assert result["recorded"] is True
    git(repo, "commit", "-m", message, *extra)
    return git(repo, "log", "-1", "--format=%B").strip("\n")


class TestTrailerMechanics:
    def test_parse_trailers_finds_block_lines(self):
        message = "subject\n\nbody text\n\nCo-Authored-By: A <a@x>\nMeridian-Ledger: 3-9\n"
        assert trailers.parse_trailers(message) == [
            ("Co-Authored-By", "A <a@x>"),
            ("Meridian-Ledger", "3-9"),
        ]

    def test_append_creates_block_after_body(self):
        out = trailers.append_trailer("subject\n\nbody\n", "Meridian-Ledger", "1")
        assert out == "subject\n\nbody\n\nMeridian-Ledger: 1"

    def test_append_joins_existing_block_and_preserves_coauthored(self):
        message = "subject\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
        out = trailers.append_trailer(message, "Meridian-Ledger", "2-4")
        # The message's trailing newline is preserved.
        assert out == (
            "subject\n\n"
            "Co-Authored-By: Claude <noreply@anthropic.com>\n"
            "Meridian-Ledger: 2-4\n"
        )

    def test_append_is_idempotent(self):
        message = "subject\n\nMeridian-Ledger: 1-2\n"
        assert trailers.append_trailer(message, "Meridian-Ledger", "9-9") == message

    def test_append_places_trailer_after_trailing_comments(self):
        message = "subject\n\nbody\n# Please enter the commit message.\n# Lines starting with # are stripped.\n"
        out = trailers.append_trailer(message, "Meridian-Ledger", "5")
        # Comments are never edited; the trailer lands at the very end and
        # git strips the comments, leaving the trailer last.
        assert out.startswith(message)
        assert out.endswith("Meridian-Ledger: 5")
        assert "# Please enter the commit message." in out

    def test_body_lines_with_colons_are_not_trailers(self):
        # A paragraph of prose containing "http: example" is not a trailer
        # block; the new trailer must start a new paragraph at the end.
        message = "subject\n\nsee http: example and time: now\n"
        out = trailers.append_trailer(message, "Meridian-Ledger", "1")
        assert out.endswith("\n\nMeridian-Ledger: 1")


class TestInstallStatusRemove:
    def test_install_status_remove_round_trip(self, repo: Path):
        installed = provenance_hooks.install(repo)
        assert installed["installed"] is True
        assert installed["alreadyInstalled"] is False
        hook = Path(installed["hookPath"])
        assert hook.exists()
        assert "Meridian-Ledger" in hook.read_text(encoding="utf-8")

        state = provenance_hooks.status(repo)
        assert state["installed"] is True
        assert state["foreignHook"] is False

        removed = provenance_hooks.remove(repo)
        assert removed["removed"] is True
        assert removed["restoredBackup"] is False
        assert not hook.exists()

    def test_install_is_idempotent(self, repo: Path):
        first = provenance_hooks.install(repo)
        second = provenance_hooks.install(repo)
        assert second["alreadyInstalled"] is True
        assert second["hookPath"] == first["hookPath"]

    def test_foreign_hook_is_backed_up_chained_and_restored(self, repo: Path):
        hooks_dir = provenance_hooks.resolve_hooks_dir(repo)
        foreign = hooks_dir / "commit-msg"
        foreign.write_text(
            "#!/bin/sh\necho 'Reviewed-by: Custom <custom@example.com>' >> \"$1\"\n",
            encoding="utf-8",
        )
        installed = provenance_hooks.install(repo)
        assert installed["chained"] is True
        backup = Path(installed["backupPath"])
        assert backup.exists()
        assert "Reviewed-by" in backup.read_text(encoding="utf-8")

        body = change_stage_record_commit(repo, "feat: chained", 1, 2)
        assert "Reviewed-by: Custom <custom@example.com>" in body
        assert "Meridian-Ledger: 1-2" in body

        removed = provenance_hooks.remove(repo)
        assert removed["restoredBackup"] is True
        assert foreign.exists()
        assert "Reviewed-by" in foreign.read_text(encoding="utf-8")

    def test_install_refuses_to_clobber_foreign_hook_with_existing_backup(
        self, repo: Path
    ):
        hooks_dir = provenance_hooks.resolve_hooks_dir(repo)
        (hooks_dir / "commit-msg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        provenance_hooks.install(repo)
        # Replace the Meridian hook with a NEW foreign hook, backup still present.
        (hooks_dir / "commit-msg").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        with pytest.raises(provenance_hooks.HookError, match="never overwrites"):
            provenance_hooks.install(repo)
        # Nothing was destroyed.
        assert (hooks_dir / "commit-msg").read_text(encoding="utf-8").endswith("exit 1\n")
        assert (hooks_dir / "commit-msg.meridian-backup").exists()

    def test_remove_leaves_foreign_hook_untouched(self, repo: Path):
        hooks_dir = provenance_hooks.resolve_hooks_dir(repo)
        foreign = hooks_dir / "commit-msg"
        foreign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        removed = provenance_hooks.remove(repo)
        assert removed["removed"] is False
        assert foreign.exists()

    def test_core_hooks_path_is_honoured(self, repo: Path, tmp_path: Path):
        custom = tmp_path / "custom-hooks"
        custom.mkdir()
        git(repo, "config", "core.hooksPath", str(custom))
        installed = provenance_hooks.install(repo)
        assert Path(installed["hookPath"]).parent == custom
        body = change_stage_record_commit(repo, "feat: custom hooks path", 4, 4)
        assert "Meridian-Ledger: 4" in body
        assert provenance_hooks.remove(repo)["removed"] is True

    def test_not_a_git_repo_reports_cleanly(self, tmp_path: Path):
        state = provenance_hooks.status(tmp_path)
        assert state["installed"] is False
        assert state["foreignHook"] is False
        assert "unavailable" in state["detail"]
        with pytest.raises(AttributionError):
            provenance_hooks.install(tmp_path)

    def test_doctor_git_hooks_check_reports_installed(self, repo: Path):
        provenance_hooks.install(repo)
        report = doctor.run_doctor(
            {"workspaceDir": str(repo)}, doctor.DoctorContext(started_at=0.0)
        )
        check = next(c for c in report["checks"] if c["id"] == "git-hooks")
        assert check["status"] == "pass"
        assert "Meridian commit-msg hook installed" in check["detail"]


class TestCommitMsgTrailerEndToEnd:
    def test_commit_carries_trailer_for_pending_range(self, repo: Path):
        provenance_hooks.install(repo)
        body = change_stage_record_commit(repo, "feat: recorded work", 10, 12)
        assert "Meridian-Ledger: 10-12" in body

    def test_single_sequence_range_has_no_dash(self, repo: Path):
        provenance_hooks.install(repo)
        body = change_stage_record_commit(repo, "feat: single", 7, 7)
        assert "Meridian-Ledger: 7" in body

    def test_second_commit_advances_the_range(self, repo: Path):
        provenance_hooks.install(repo)
        first = change_stage_record_commit(repo, "feat: first recorded", 1, 3)
        assert "Meridian-Ledger: 1-3" in first
        second = change_stage_record_commit(repo, "feat: second recorded", 4, 6)
        assert "Meridian-Ledger: 4-6" in second

    def test_commit_without_pending_record_has_no_trailer(self, repo: Path):
        provenance_hooks.install(repo)
        body = change_stage_record_commit(repo, "feat: unrecorded")
        assert "Meridian-Ledger" not in body

    def test_existing_coauthored_by_is_preserved(self, repo: Path):
        provenance_hooks.install(repo)
        body = change_stage_record_commit(
            repo,
            "feat: with agent",
            8,
            9,
            "-m",
            "Co-Authored-By: Claude <noreply@anthropic.com>",
        )
        assert "Co-Authored-By: Claude <noreply@anthropic.com>" in body
        assert "Meridian-Ledger: 8-9" in body

    def test_hook_entry_point_is_idempotent(self, repo: Path):
        provenance_hooks.install(repo)
        git(repo, "add", "file.txt")
        msg_file = repo / "msg.txt"
        msg_file.write_text("feat: direct\n", encoding="utf-8")
        staged_hash = git(repo, "write-tree").strip()
        provenance_hooks.record_pending(repo, staged_hash, 2, 2)
        assert provenance_hooks.commit_msg(repo, msg_file) == 0
        once = msg_file.read_text(encoding="utf-8")
        assert once.count("Meridian-Ledger") == 1
        # Second run: record already consumed, trailer already present.
        assert provenance_hooks.commit_msg(repo, msg_file) == 0
        assert msg_file.read_text(encoding="utf-8") == once

    def test_consumed_record_is_archived_with_trailers(self, repo: Path):
        provenance_hooks.install(repo)
        change_stage_record_commit(repo, "feat: archived", 5, 5)
        attributions = repo / ".meridian" / "hooks" / "attributions.jsonl"
        lines = [
            line for line in attributions.read_text(encoding="utf-8").splitlines()
        ]
        assert len(lines) == 1
        import json

        record = json.loads(lines[0])
        assert record["fromSequence"] == 5
        assert record["consumed"] is True
        # Pending list is drained; only open records remain.
        pending = repo / ".meridian" / "hooks" / "pending.json"
        assert pending.exists()
        assert json.loads(pending.read_text(encoding="utf-8")) == []


class TestHookPendingValidation:
    def test_rejects_inverted_or_nonpositive_ranges(self, repo: Path):
        with pytest.raises(provenance_hooks.HookError, match="fromSequence"):
            provenance_hooks.record_pending(repo, "abc", 3, 2)
        with pytest.raises(provenance_hooks.HookError, match="fromSequence"):
            provenance_hooks.record_pending(repo, "abc", 0, 2)
        with pytest.raises(provenance_hooks.HookError, match="stagedHash"):
            provenance_hooks.record_pending(repo, "", 1, 2)


class TestHookRpc:
    def _server(self, repo: Path) -> SidecarServer:
        server = SidecarServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {
                    "protocolVersion": protocol.PROTOCOL_VERSION,
                    "client": "pytest",
                    "workspaceDir": str(repo),
                },
            }
        )
        assert response is not None and "result" in response
        return server

    def _call(self, server: SidecarServer, method: str, params: dict, seq: int):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": seq, "method": method, "params": params}
        )
        assert response is not None
        return response

    def test_install_status_remove_over_the_bus(self, repo: Path):
        server = self._server(repo)
        installed = self._call(server, "hook/install", {}, 2)
        assert installed["result"]["installed"] is True

        status = self._call(server, "hook/status", {}, 3)
        assert status["result"]["installed"] is True

        removed = self._call(server, "hook/remove", {}, 4)
        assert removed["result"]["removed"] is True

    def test_pending_over_the_bus_and_end_to_end_commit(self, repo: Path):
        server = self._server(repo)
        self._call(server, "hook/install", {}, 2)
        # Stage the change first, then link THAT staged content to the range
        # over the bus, then commit without further worktree edits.
        (repo / "file.txt").write_text("feat: via rpc\n", encoding="utf-8")
        git(repo, "add", "file.txt")
        staged_hash = git(repo, "write-tree").strip()
        recorded = self._call(
            server,
            "hook/pending",
            {"stagedHash": staged_hash, "fromSequence": 11, "toSequence": 14},
            3,
        )
        assert recorded["result"]["recorded"] is True
        body = commit(repo, "feat: via rpc")
        assert "Meridian-Ledger: 11-14" in body

    def test_pending_validation_error_is_actionable(self, repo: Path):
        server = self._server(repo)
        response = self._call(
            server, "hook/pending", {"stagedHash": "x", "fromSequence": 2,
                                     "toSequence": 1}, 2
        )
        assert response["error"]["code"] == protocol.INVALID_PARAMS
        assert "fromSequence" in response["error"]["message"]

    def test_install_without_workspace_is_a_params_error(self, tmp_path: Path):
        server = SidecarServer()
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "hook/install", "params": {}}
        )
        assert response is not None
        assert response["error"]["code"] == protocol.INVALID_PARAMS
