"""Devin observer tests (FR-M35-02, FR-M35-08, NFR-32, D20; task 30).

Devin is an inferred-confidence observer: `direct` requires an ACP session
hosted by Meridian (F1 hosted agents) and is structurally impossible here
(the git tier caps at `telemetry`, the state-dir tier at `inferred`).
Every tier failure degrades to a visible warning. No evidence anywhere is
honest `None` — never a fabricated session; a bare workspace burst is
deliberately NOT Devin evidence.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meridian_core.observers.base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_TELEMETRY,
    TelemetryFormatError,
)
from meridian_core.observers.devin import NO_DIRECT_WARNING, DevinObserver, is_devin_author
from test_attribution import git

NOW = datetime(2025, 9, 20, 12, 10, tzinfo=timezone.utc)

DEVIN_BOT = ("devin-ai-integration[bot]", "devin-ai-integration[bot]@users.noreply.github.com")


def commit_by_devin(repo: Path, when: int | None = None) -> None:
    when = when or int(NOW.timestamp()) - 120
    (repo / "src" / "devin.txt").write_text("devin wrote this\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feat: devin change", author=DEVIN_BOT, date=when)


def commit_coauthored_devin(repo: Path, when: int | None = None) -> None:
    when = when or int(NOW.timestamp()) - 120
    (repo / "src" / "devin2.txt").write_text("devin co-authored\n", encoding="utf-8")
    git(repo, "add", ".")
    message = (
        "feat: human landed devin work\n\n"
        "Co-Authored-By: devin-ai-integration[bot] "
        "<devin-ai-integration[bot]@users.noreply.github.com>\n"
    )
    git(repo, "commit", "-m", message, date=when)


def make_observer(tmp_path: Path, **kwargs) -> DevinObserver:
    kwargs.setdefault("env", {})
    return DevinObserver(**kwargs)


class TestGitAttributionTier:
    def test_bot_authored_commit_yields_telemetry(self, repo):
        commit_by_devin(repo)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY
        assert outcome.observation.source == CHAIN_GIT_TRAILERS
        assert outcome.observation.vendor == "devin"
        assert outcome.observation.session_id.startswith("git:")

    def test_bot_coauthored_commit_yields_telemetry(self, repo):
        commit_coauthored_devin(repo)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY

    def test_commits_outside_window_are_not_evidence(self, repo):
        commit_by_devin(repo, when=int(NOW.timestamp()) - 6 * 3600)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None

    def test_human_commits_are_not_evidence(self, repo):
        (repo / "src" / "human.txt").write_text("human work\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "human change")
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None

    def test_git_tier_failure_warns_and_degrades(self, repo, tmp_path):
        # A git-tier failure (NFR-32) must downgrade WITH a visible
        # warning, never silence.
        state_dir = tmp_path / "devin-state"
        session = state_dir / "sessions"
        session.mkdir(parents=True)
        recent = session / "run-1.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        observer = DevinObserver(state_dir=state_dir)

        def broken(workspace, now):
            raise TelemetryFormatError("git log format unreachable")

        observer._scan_git = broken
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_GIT_TRAILERS
        assert outcome.warnings and "NFR-32" in outcome.warnings[0]
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM


class TestBotIdentityMatching:
    def test_is_devin_author(self):
        for name, email, expected in [
            ("devin-ai-integration[bot]", DEVIN_BOT[1], True),
            ("devin[bot]", "devin[bot]@users.noreply.github.com", True),
            ("Devin Smith", "devin.smith@example.com", False),  # human named Devin
            ("someone", "devin.fan@example.com", False),  # no [bot] marker
            ("github-actions[bot]", "github-actions@users.noreply.github.com", False),
            ("human", "human@example.com", False),
        ]:
            assert is_devin_author(name, email) is expected, (name, email)


class TestStateDirTier:
    def test_recent_state_write_yields_inferred(self, tmp_path):
        state_dir = tmp_path / "devin-state"
        session = state_dir / "sessions"
        session.mkdir(parents=True)
        recent = session / "run-9.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        observer = DevinObserver(state_dir=state_dir)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM
        assert "inferred" in outcome.observation.detail

    def test_state_dir_env_var_is_honoured(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "devin-state-env"
        session = state_dir / "sessions"
        session.mkdir(parents=True)
        recent = session / "run-env.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        monkeypatch.setenv("MERIDIAN_DEVIN_STATE_DIR", str(state_dir))
        observer = DevinObserver(env=dict(os.environ))
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED

    def test_stale_state_write_is_not_evidence(self, tmp_path):
        state_dir = tmp_path / "devin-state"
        session = state_dir / "sessions"
        session.mkdir(parents=True)
        stale = session / "run-old.json"
        stale.write_text("{}", encoding="utf-8")
        os.utime(stale, (NOW.timestamp() - 6 * 3600, NOW.timestamp() - 6 * 3600))
        observer = DevinObserver(state_dir=state_dir)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is None

    def test_unconfigured_state_dir_is_unavailable_not_drift(self, tmp_path):
        observer = make_observer(tmp_path)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.degraded_from is None


class TestHonesty:
    def test_no_evidence_anywhere_is_honest_none(self, repo):
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None
        assert outcome.warnings == []

    def test_bare_write_burst_is_not_devin_evidence(self, repo):
        # Unlike in-editor assistants, an unattributed burst cannot carry
        # the Devin vendor tag — fabrication is worse than silence here,
        # and NFR-32 silence is not an option either: None + a health note.
        (repo / "src" / "burst.txt").write_text("line\n" * 40, encoding="utf-8")
        observer = make_observer(repo)
        outcome = observer.observe(repo, datetime.now(timezone.utc))
        assert outcome.observation is None

    def test_direct_is_never_claimed(self, repo, tmp_path):
        commit_by_devin(repo)
        state_dir = tmp_path / "devin-state"
        session = state_dir / "sessions"
        session.mkdir(parents=True)
        recent = session / "run-live.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 30, NOW.timestamp() - 30))
        observer = DevinObserver(state_dir=state_dir)
        for when in (NOW, NOW + timedelta(minutes=1)):
            outcome = observer.observe(repo, when)
            assert outcome.observation is not None
            assert outcome.observation.confidence != CONFIDENCE_DIRECT

    def test_mandated_warning_text_is_exposed(self):
        assert "`direct` confidence " in NO_DIRECT_WARNING
        assert "ACP" in NO_DIRECT_WARNING
        observer = DevinObserver(env={})
        assert NO_DIRECT_WARNING in observer.health()["detail"]

    def test_observer_is_versioned(self):
        observer = make_observer(Path("."))
        assert observer.vendor == "devin"
        assert observer.vendor_release
        assert observer.adapter_version
