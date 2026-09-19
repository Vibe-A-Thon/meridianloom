"""Rejection capture (F0 Workstream F task 28; FR-M37-01 subset).

Fixture repositories are built with pinned dates so the configurable window
(``meridian.rejectionWindowDays``, default 7 days) is exercised exactly:
inside the window -> replaced_within_window, outside -> no record.

The three rejection shapes:
* reverted — a later commit removes the change's added lines and restores
  the lines it removed;
* force_amended — the commit is unreachable from HEAD (reflog evidence)
  and its content no longer exists at HEAD;
* replaced_within_window — a later commit rewrites the change's lines with
  different content within windowDays of the change's commit date.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bus_types

from meridian_core import rejection as rejection_mod
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.server import SidecarServer
from test_attribution import ALICE, BOB, CAROL, T0, git

DAY = 86_400


def _repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial", date=T0)
    return tmp_path


def _replace_two(repo: Path, new_line: str, author=BOB, date=T0 + 600) -> str:
    (repo / "src" / "app.txt").write_text(f"one\n{new_line}\nthree\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", f"change to {new_line}", author=author, date=date)
    return git(repo, "rev-parse", "HEAD").strip()


class TestReverted:
    def test_revert_is_detected_with_restoring_commit(self, repo):
        rejected = _replace_two(repo, "two-agent")
        rejecting = _replace_two(repo, "two", author=CAROL, date=T0 + 1200)

        rejections = rejection_mod.detect(repo)

        assert len(rejections) == 1
        (rejection,) = rejections
        assert rejection.reason == rejection_mod.REASON_REVERTED
        assert rejection.rejected_commit == rejected
        assert rejection.rejecting_commit == rejecting
        assert rejection.paths == ("src/app.txt",)
        assert rejection.lines_rejected == 1
        assert rejection.rejected_at == "2023-11-14T22:33:20+00:00"

    def test_manual_revert_restoring_prior_content(self, repo):
        # Same shape, but the restoring commit also carries unrelated work:
        # the restore rule is per-line, not per-commit.
        rejected = _replace_two(repo, "two-agent")
        (repo / "README.md").write_text("hello\nnotes\n", encoding="utf-8")
        (repo / "src" / "app.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "restore two + notes", author=CAROL, date=T0 + 1200)

        rejections = rejection_mod.detect(repo)

        assert [r.reason for r in rejections] == [rejection_mod.REASON_REVERTED]
        assert rejections[0].rejected_commit == rejected


class TestForceAmended:
    def test_amended_away_change_is_detected(self, repo):
        _replace_two(repo, "two-agent")
        amended_sha = git(repo, "rev-parse", "HEAD").strip()
        # Force-amend: the agent's line disappears from the commit's final form.
        (repo / "src" / "app.txt").write_text("one\ntwo-rewritten\nthree\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "--amend", "--no-edit", author=BOB, date=T0 + 900)

        rejections = rejection_mod.detect(repo)

        force_amends = [r for r in rejections if r.reason == rejection_mod.REASON_FORCE_AMENDED]
        assert len(force_amends) == 1
        (rejection,) = force_amends
        assert rejection.rejected_commit == amended_sha
        assert rejection.rejecting_commit is None
        assert rejection.paths == ("src/app.txt",)
        # The amended-in content stands: no revert/replacement rejection.
        assert [r for r in rejections if r.reason != rejection_mod.REASON_FORCE_AMENDED] == []

    def test_rebased_without_change_is_not_force_amended(self, repo):
        # Unreachable-but-identical content (rebase) is not a rejection:
        # the lines still exist at HEAD.
        _replace_two(repo, "two-agent")
        original = git(repo, "rev-parse", "HEAD").strip()
        git(repo, "checkout", "--detach", "HEAD")
        git(repo, "commit", "--amend", "--no-edit", author=BOB, date=T0 + 900)
        amended = git(repo, "rev-parse", "HEAD").strip()
        assert amended != original

        rejections = rejection_mod.detect(repo)

        assert [r for r in rejections if r.rejected_commit == original] == []


@pytest.mark.slow
class TestReplacedWithinWindow:
    def test_replacement_inside_window_is_detected(self, repo):
        rejected = _replace_two(repo, "two-agent")
        rejecting = _replace_two(repo, "two-better", author=CAROL, date=T0 + 1200)

        rejections = rejection_mod.detect(repo)

        assert len(rejections) == 1
        (rejection,) = rejections
        assert rejection.reason == rejection_mod.REASON_REPLACED_WITHIN_WINDOW
        assert rejection.rejected_commit == rejected
        assert rejection.rejecting_commit == rejecting

    def test_replacement_outside_window_is_not_rejected(self, repo):
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two-better", author=CAROL, date=T0 + 8 * DAY)

        assert rejection_mod.detect(repo) == []

    def test_window_boundary_is_inclusive(self, repo):
        # Exactly 7 days later: inside the default window -> rejected.
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two-better", author=CAROL, date=T0 + 7 * DAY)

        rejections = rejection_mod.detect(repo)

        assert [r.reason for r in rejections] == [rejection_mod.REASON_REPLACED_WITHIN_WINDOW]

    def test_window_boundary_plus_one_step_is_outside(self, repo):
        # The change lands at T0+600; 7 days + one 10-minute step later is
        # strictly outside the default 7-day window.
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two-better", author=CAROL, date=T0 + 7 * DAY + 1200)

        assert rejection_mod.detect(repo) == []

    def test_custom_window_is_respected(self, repo):
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two-better", author=CAROL, date=T0 + 3 * DAY)

        # A 2-day window misses the 3-day replacement; a 3-day window catches it.
        assert rejection_mod.detect(repo, window_days=2) == []
        rejections = rejection_mod.detect(repo, window_days=3)
        assert [r.reason for r in rejections] == [rejection_mod.REASON_REPLACED_WITHIN_WINDOW]

    def test_invalid_window_is_a_clean_error(self, repo):
        with pytest.raises(rejection_mod.AttributionError, match="window_days"):
            rejection_mod.detect(repo, window_days=0)


class TestNotRejected:
    def test_surviving_change_produces_no_record(self, repo):
        _replace_two(repo, "two-agent")

        assert rejection_mod.detect(repo) == []

    def test_initial_commit_is_not_rejected(self, repo):
        # Only the initial commit exists: nothing to reject.
        assert rejection_mod.detect(repo) == []

    def test_base_limits_the_walk(self, repo):
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two-better", author=CAROL, date=T0 + 1200)
        base = git(repo, "rev-parse", "HEAD").strip()

        # Excluding the rejecting commit's history sees no rejection.
        assert rejection_mod.detect(repo, base=base) == []


@pytest.mark.slow
class TestDetectRejectionsRpc:
    """trust/detectRejections over the dispatch layer: ledger recording,
    idempotency, trailer-based sequence resolution, tier ownership."""

    @pytest.fixture()
    def server(self, tmp_path):
        ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
        instance = SidecarServer(ledger=ledger)
        yield instance
        ledger.close()

    def _call(self, server, method, params):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 5, "method": method, "params": params}
        )
        assert response is not None
        assert "error" not in response, response.get("error")
        return response["result"]

    def _reverted_repo(self, tmp_path):
        repo = _repo(tmp_path)
        _replace_two(repo, "two-agent")
        _replace_two(repo, "two", author=CAROL, date=T0 + 1200)
        return repo

    def test_rejection_is_recorded_in_the_ledger(self, server, tmp_path):
        repo = self._reverted_repo(tmp_path / "repo")
        result = self._call(
            server, "trust/detectRejections", {"repoPath": str(repo), "repoId": "edb"}
        )

        assert result["recorded"] == 1
        assert result["duplicatesSkipped"] == 0
        (rejection,) = result["rejections"]
        assert rejection["reason"] == "reverted"
        assert rejection["rejectingCommit"]
        assert rejection["recordedSequence"] == 1

        entries = server.ledger.query(action_type="rejection")
        assert len(entries) == 1
        entry = entries[0]
        # Distinct action type carrying the linkage columns.
        assert entry["action_type"] == "rejection"
        assert entry["rejected_commit"] == rejection["rejectedCommit"]
        assert entry["rejecting_commit"] == rejection["rejectingCommit"]
        # E-GR-03: no human classification supplied -> fail-closed default
        # with an explanatory note; the mechanical shape stays alongside.
        assert entry["rework_reason"] == "other"
        detail = json.loads(entry["tool_calls"])
        assert detail[0]["shape"] == "reverted"
        assert "requires human classification" in detail[0]["reasonNote"]
        assert rejection["reworkReason"] == "other"
        assert "requires human classification" in rejection["reasonNote"]
        assert entry["decision"] == "rejected"
        assert entry["repo_id"] == "edb"
        assert entry["story_id"] == "untracked"  # no trailer link: caller fallback
        assert entry["actor_id"] == "unknown"

    def test_second_run_is_idempotent(self, server, tmp_path):
        repo = self._reverted_repo(tmp_path / "repo")
        params = {"repoPath": str(repo), "repoId": "edb"}
        first = self._call(server, "trust/detectRejections", params)
        second = self._call(server, "trust/detectRejections", params)

        assert first["recorded"] == 1
        assert second["recorded"] == 0
        assert second["duplicatesSkipped"] == 1
        assert second["rejections"][0]["alreadyRecorded"] is True
        assert second["rejections"][0]["recordedSequence"] == 1
        assert len(server.ledger.query(action_type="rejection")) == 1

    def test_meridian_ledger_trailer_resolves_the_rejected_sequence(self, server, tmp_path):
        repo = _repo(tmp_path / "repo")
        # The rejected commit carries the hook's Meridian-Ledger trailer.
        (repo / "src" / "app.txt").write_text("one\ntwo-agent\nthree\n", encoding="utf-8")
        git(repo, "add", ".")
        git(
            repo,
            "commit",
            "-m",
            "change to two-agent\n\nMeridian-Ledger: 41-43",
            author=BOB,
            date=T0 + 600,
        )
        _replace_two(repo, "two", author=CAROL, date=T0 + 1200)

        result = self._call(
            server, "trust/detectRejections", {"repoPath": str(repo), "repoId": "edb"}
        )

        (rejection,) = result["rejections"]
        assert rejection["rejectedSequence"] == 41
        entry = server.ledger.query(action_type="rejection")[0]
        assert entry["rejected_sequence"] == 41

    def test_window_days_param_is_validated(self, server, tmp_path):
        repo = self._reverted_repo(tmp_path / "repo")
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "trust/detectRejections",
                "params": {"repoPath": str(repo), "windowDays": 0},
            }
        )
        assert response["error"]["code"] == bus_types.INVALID_PARAMS

    def test_no_repo_path_is_a_params_error(self, server):
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 7, "method": "trust/detectRejections", "params": {}}
        )
        assert response["error"]["code"] == bus_types.INVALID_PARAMS

    def test_owned_by_flight_recorder_capability(self):
        owning = [
            capability
            for capability in bus_types.CAPABILITIES
            if "trust/detectRejections" in capability["rpcMethods"]
        ]
        assert len(owning) == 1
        assert owning[0]["tier"] == "flight-recorder"

    def test_method_listed_in_handshake_capabilities(self, server):
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "handshake",
                "params": {"protocolVersion": bus_types.PROTOCOL_VERSION, "client": "pytest"},
            }
        )
        methods = response["result"]["capabilities"]["methods"]
        assert "trust/detectRejections" in methods
