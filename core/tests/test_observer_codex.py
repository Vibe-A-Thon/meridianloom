"""Codex observer tests (FR-M35-02, FR-M35-08, NFR-32, D20; task 30).

Codex is an inferred-confidence observer: `direct` is structurally
impossible (the trailer tier caps at `telemetry`, the session-file tier at
`inferred`), and every tier failure degrades to a visible warning. No
telemetry anywhere is honest `None` — never a fabricated session.
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
from meridian_core.observers.codex import NO_DIRECT_WARNING, CodexObserver
from test_attribution import git

NOW = datetime(2025, 9, 20, 12, 10, tzinfo=timezone.utc)


def commit_codex(repo: Path, when: int | None = None) -> None:
    when = when or int(NOW.timestamp()) - 120
    (repo / "src" / "codex.txt").write_text("codex wrote this\n", encoding="utf-8")
    git(repo, "add", ".")
    message = "feat: codex change\n\nCo-Authored-By: Codex <codex@openai.com>\n"
    git(repo, "commit", "-m", message, date=when)


def make_observer(tmp_path: Path, **kwargs) -> CodexObserver:
    kwargs.setdefault("codex_home", tmp_path / "no-codex-home")
    return CodexObserver(**kwargs)


def write_session(codex_home: Path, age_seconds: float, name: str) -> Path:
    session = codex_home / "sessions" / "2025" / "09" / "20" / name
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text('{"timestamp": "2025-09-20T12:00:00Z"}\n', encoding="utf-8")
    os.utime(
        session,
        (NOW.timestamp() - age_seconds, NOW.timestamp() - age_seconds),
    )
    return session


class TestTrailerTier:
    def test_coauthored_trailer_yields_telemetry(self, repo):
        commit_codex(repo)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY
        assert outcome.observation.source == CHAIN_GIT_TRAILERS
        assert outcome.observation.vendor == "codex"
        assert outcome.observation.session_id.startswith("git:")

    def test_trailers_outside_window_are_not_evidence(self, repo):
        commit_codex(repo, when=int(NOW.timestamp()) - 6 * 3600)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None

    def test_plain_commits_are_not_evidence(self, repo):
        (repo / "src" / "human.txt").write_text("human work\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "human change")
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None

    def test_trailer_tier_failure_warns_and_degrades(self, repo, tmp_path):
        # A trailer-tier format change (NFR-32) must downgrade WITH a
        # visible warning, never silence.
        codex_home = tmp_path / "codex-home"
        write_session(codex_home, age_seconds=60, name="rollout-1726-session-9.jsonl")
        observer = CodexObserver(codex_home=codex_home)

        def broken(workspace, now):
            raise TelemetryFormatError("codex trailer grammar changed")

        observer._scan_trailers = broken
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_GIT_TRAILERS
        assert outcome.warnings and "NFR-32" in outcome.warnings[0]
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM


class TestSessionFileTier:
    def test_recent_rollout_yields_inferred(self, tmp_path):
        codex_home = tmp_path / "codex-home"
        write_session(
            codex_home, age_seconds=60, name="rollout-2025-09-20T12-00-00-abc123.jsonl"
        )
        observer = CodexObserver(codex_home=codex_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM
        assert "abc123" in outcome.observation.session_id
        assert "content is not parsed" in outcome.observation.detail

    def test_stale_rollout_is_not_evidence(self, tmp_path):
        codex_home = tmp_path / "codex-home"
        write_session(
            codex_home, age_seconds=6 * 3600, name="rollout-old-session.jsonl"
        )
        observer = CodexObserver(codex_home=codex_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is None

    def test_unstructured_rollout_name_still_reports_inferred(self, tmp_path):
        # The filename shape is never a parse dependency: an unexpected
        # name degrades the session id, never the observation.
        codex_home = tmp_path / "codex-home"
        write_session(codex_home, age_seconds=60, name="whatever.jsonl")
        observer = CodexObserver(codex_home=codex_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert "whatever" in outcome.observation.session_id


class TestHonesty:
    def test_no_evidence_anywhere_is_honest_none(self, repo):
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None
        assert outcome.warnings == []

    def test_direct_is_never_claimed(self, repo, tmp_path):
        commit_codex(repo)
        codex_home = tmp_path / "codex-home"
        write_session(codex_home, age_seconds=30, name="rollout-live.jsonl")
        observer = CodexObserver(codex_home=codex_home)
        for when in (NOW, NOW + timedelta(minutes=1)):
            outcome = observer.observe(repo, when)
            assert outcome.observation is not None
            assert outcome.observation.confidence != CONFIDENCE_DIRECT

    def test_mandated_warning_text_is_exposed(self):
        assert "`direct` confidence " in NO_DIRECT_WARNING
        observer = CodexObserver(codex_home=Path("/no/such/codex-home"))
        assert NO_DIRECT_WARNING in observer.health()["detail"]

    def test_observer_is_versioned(self):
        observer = make_observer(Path("."))
        assert observer.vendor == "codex"
        assert observer.vendor_release
        assert observer.adapter_version
