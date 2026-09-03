"""Copilot observer tests (FR-M35-02, FR-M35-03, NFR-32; task 19).

The SCM/PR tier is proven against a recorded real `gh api` response shape
(checked-in fixture — field names come from the GitHub API, never
invented) with an injected runner: no gh binary required, zero
credentials. Availability, drift, and the inferred floor are all covered.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meridian_core.observers.base import (
    CHAIN_FILESYSTEM,
    CHAIN_SCM_API,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
)
from meridian_core.observers.copilot import (
    CopilotObserver,
    github_repo_slug,
    is_copilot_pr,
)
from test_attribution import git

FIXTURE_PULLS = Path(__file__).parent / "fixtures" / "gh_api" / "pulls.json"
NOW = datetime(2025, 9, 20, 12, 10, tzinfo=timezone.utc)
SLUG = "acme/payments"


def repo_with_remote(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "init")
    git(repo, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    return repo


def fixture_runner(stdout_override: str | None = None, code: int = 0):
    """A Runner answering like `gh api` with the recorded fixture."""

    calls: list[list[str]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(list(argv))
        stdout = (
            FIXTURE_PULLS.read_text(encoding="utf-8")
            if stdout_override is None
            else stdout_override
        )
        return code, stdout, "" if code == 0 else "gh: HTTP 401"

    runner.calls = calls
    return runner


class TestPrAttribution:
    def test_copilot_prs_are_detected_with_direct_confidence(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        observer = CopilotObserver(runner=fixture_runner(), gh_path="/usr/bin/gh")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_DIRECT
        assert outcome.observation.source == CHAIN_SCM_API
        assert outcome.observation.vendor == "copilot"
        # PRs 41 and 40 are in the window; 39 is human, 38 is too old.
        assert "2 Copilot-authored PR(s)" in outcome.observation.detail
        assert "copilot-swe-agent" in outcome.observation.detail
        assert outcome.observation.session_id == f"pr:{SLUG}#41"

    def test_no_credentials_are_needed_runner_is_injected(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        runner = fixture_runner()
        observer = CopilotObserver(runner=runner, gh_path="/usr/bin/gh")
        observer.observe(repo, NOW)
        (call,) = runner.calls
        assert call[0] == "/usr/bin/gh" and call[1] == "api"
        assert f"repos/{SLUG}/pulls" in call

    def test_human_only_prs_are_not_evidence(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        human_only = json.dumps(
            [p for p in json.loads(FIXTURE_PULLS.read_text(encoding="utf-8")) if p["user"]["login"] == "sindhu"]
        )
        observer = CopilotObserver(
            runner=fixture_runner(stdout_override=human_only), gh_path="/usr/bin/gh"
        )
        outcome = observer.observe(repo, NOW)
        # Falls through SCM tier (no Copilot PRs) — no fs activity here.
        assert outcome.observation is None

    def test_old_prs_outside_window_are_not_evidence(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        observer = CopilotObserver(runner=fixture_runner(), gh_path="/usr/bin/gh")
        outcome = observer.observe(repo, NOW + timedelta(days=3))
        assert outcome.observation is None

    def test_api_shape_change_is_vendor_drift_with_warning(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        # HTTP 200 but the payload is no longer the GitHub API list shape.
        observer = CopilotObserver(
            runner=fixture_runner(stdout_override=json.dumps({"total_count": 4})),
            gh_path="/usr/bin/gh",
        )
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_SCM_API
        assert outcome.warnings and "NFR-32" in outcome.warnings[0]

    def test_broken_timestamps_are_vendor_drift(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        pulls = json.loads(FIXTURE_PULLS.read_text(encoding="utf-8"))
        for pull in pulls:
            pull["updated_at"] = "not-a-date"
        observer = CopilotObserver(
            runner=fixture_runner(stdout_override=json.dumps(pulls)),
            gh_path="/usr/bin/gh",
        )
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_SCM_API
        assert outcome.warnings

    def test_unauthenticated_or_unreachable_api_is_unavailable_not_drift(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        observer = CopilotObserver(runner=fixture_runner(code=1), gh_path="/usr/bin/gh")
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from is None
        assert outcome.observation is None
        assert outcome.warnings == []

    def test_missing_gh_is_unavailable_not_drift(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        observer = CopilotObserver(gh_path="")
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from is None
        assert outcome.observation is None

    def test_repo_without_github_remote_is_unavailable(self, tmp_path):
        repo = tmp_path / "plain"
        repo.mkdir()
        git(repo, "init")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "init")
        runner = fixture_runner()
        observer = CopilotObserver(runner=runner, gh_path="/usr/bin/gh")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None
        assert runner.calls == []  # no probe fired without a slug


class TestInEditorInference:
    def test_write_burst_with_no_session_is_inferred(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        (repo / "src.py").write_text("x = 1\n" * 30, encoding="utf-8")
        observer = CopilotObserver(gh_path="")
        outcome = observer.observe(repo, datetime.now(timezone.utc))
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM
        assert "inferred" in outcome.observation.detail

    def test_quiet_workspace_is_honest_none(self, tmp_path):
        repo = repo_with_remote(tmp_path)
        observer = CopilotObserver(gh_path="")
        outcome = observer.observe(repo, datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert outcome.observation is None


class TestCopilotDetectionHelpers:
    @pytest.mark.parametrize(
        "login,kind,ref,title,expected",
        [
            ("copilot-swe-agent", "User", "copilot/x", "t", True),
            ("copilot-sweeper", "User", "copilot/x", "t", True),
            ("github-copilot[bot]", "Bot", "copilot/x", "t", True),
            ("some-copilot-helper", "Bot", "other", "t", True),
            ("sindhu", "User", "fix/thing", "t", False),
            ("sindhu", "User", "copilot/looks-cop", "human branch", True),
            ("sindhu", "User", "feature", "Copilot: draft", True),
        ],
    )
    def test_is_copilot_pr(self, login, kind, ref, title, expected):
        pull = {
            "user": {"login": login, "type": kind},
            "head": {"ref": ref},
            "title": title,
        }
        assert is_copilot_pr(pull) is expected

    def test_slug_parsing_https_and_ssh(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        git(repo, "init")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "init")
        git(repo, "remote", "add", "origin", "https://github.com/owner/name.git")
        for url in (
            "https://github.com/owner/name.git",
            "https://github.com/owner/name",
            "git@github.com:owner/name.git",
        ):
            git(repo, "remote", "set-url", "origin", url)
            assert github_repo_slug(repo) == "owner/name", url

    def test_observer_is_versioned(self):
        observer = CopilotObserver(gh_path="")
        assert observer.vendor == "copilot"
        assert observer.vendor_release
        assert observer.adapter_version
