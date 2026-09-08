"""Cursor observer tests (FR-M35-02, FR-M35-08, NFR-32, D20; task 30).

Cursor is an inferred-confidence observer: `direct` is structurally
impossible (the trailer tier caps at `telemetry`, the filesystem tier at
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
from meridian_core.observers.cursor import NO_DIRECT_WARNING, CursorObserver
from test_attribution import git

NOW = datetime(2025, 9, 20, 12, 10, tzinfo=timezone.utc)


def commit_cursor(repo: Path, when: int | None = None) -> None:
    when = when or int(NOW.timestamp()) - 120
    (repo / "src" / "cursor.txt").write_text("cursor wrote this\n", encoding="utf-8")
    git(repo, "add", ".")
    message = "feat: cursor change\n\nCo-Authored-By: Cursor <cursor@anysphere.inc>\n"
    git(repo, "commit", "-m", message, date=when)


def make_observer(tmp_path: Path, **kwargs) -> CursorObserver:
    kwargs.setdefault("cursor_home", tmp_path / "no-cursor-home")
    return CursorObserver(**kwargs)


class TestTrailerTier:
    def test_coauthored_trailer_yields_telemetry(self, repo):
        commit_cursor(repo)
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY
        assert outcome.observation.source == CHAIN_GIT_TRAILERS
        assert outcome.observation.vendor == "cursor"
        assert outcome.observation.session_id.startswith("git:")

    def test_alt_cursor_mailbox_also_attributes(self, repo):
        when = int(NOW.timestamp()) - 120
        (repo / "src" / "alt.txt").write_text("x\n", encoding="utf-8")
        git(repo, "add", ".")
        git(
            repo,
            "commit",
            "-m",
            "feat: alt\n\nCo-Authored-By: Cursor <cursor@cursor.com>\n",
            date=when,
        )
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation.confidence == CONFIDENCE_TELEMETRY

    def test_trailers_outside_window_are_not_evidence(self, repo):
        commit_cursor(repo, when=int(NOW.timestamp()) - 6 * 3600)
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
        cursor_home = tmp_path / "cursor-home"
        state = cursor_home / "chats" / "ws"
        state.mkdir(parents=True)
        recent = state / "chat-1.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        observer = CursorObserver(cursor_home=cursor_home)
        original = observer._scan_trailers

        def broken(workspace, now):
            raise TelemetryFormatError("cursor trailer grammar changed")

        observer._scan_trailers = broken
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_GIT_TRAILERS
        assert outcome.warnings and "NFR-32" in outcome.warnings[0]
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM
        observer._scan_trailers = original


class TestFilesystemTier:
    def test_recent_state_home_write_yields_inferred(self, tmp_path):
        cursor_home = tmp_path / "cursor-home"
        state = cursor_home / "chats" / "ws"
        state.mkdir(parents=True)
        recent = state / "chat-1.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        observer = CursorObserver(cursor_home=cursor_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM
        assert "inferred" in outcome.observation.detail

    def test_state_home_existence_alone_is_not_evidence(self, tmp_path):
        cursor_home = tmp_path / "cursor-home"
        state = cursor_home / "chats" / "ws"
        state.mkdir(parents=True)
        stale = state / "chat-old.json"
        stale.write_text("{}", encoding="utf-8")
        os.utime(stale, (NOW.timestamp() - 6 * 3600, NOW.timestamp() - 6 * 3600))
        observer = CursorObserver(cursor_home=cursor_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is None

    def test_cursorrules_plus_burst_yields_inferred(self, repo):
        (repo / ".cursorrules").write_text("always test\n", encoding="utf-8")
        (repo / "src" / "burst.txt").write_text("line\n" * 40, encoding="utf-8")
        observer = make_observer(repo)
        outcome = observer.observe(repo, datetime.now(timezone.utc))
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert ".cursorrules" in outcome.observation.detail

    def test_burst_without_marker_is_unattributed(self, repo):
        # No Cursor marker, no state home: a bare burst cannot carry the
        # Cursor vendor tag (that would fabricate attribution).
        (repo / "src" / "burst.txt").write_text("line\n" * 40, encoding="utf-8")
        observer = make_observer(repo)
        outcome = observer.observe(repo, datetime.now(timezone.utc))
        assert outcome.observation is None


class TestHonesty:
    def test_no_evidence_anywhere_is_honest_none(self, repo):
        observer = make_observer(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None
        assert outcome.warnings == []

    def test_direct_is_never_claimed(self, repo, tmp_path):
        commit_cursor(repo)
        cursor_home = tmp_path / "cursor-home"
        state = cursor_home / "compose"
        state.mkdir(parents=True)
        recent = state / "compose-1.json"
        recent.write_text("{}", encoding="utf-8")
        os.utime(recent, (NOW.timestamp() - 30, NOW.timestamp() - 30))
        observer = CursorObserver(cursor_home=cursor_home)
        for when in (NOW, NOW + timedelta(minutes=1)):
            outcome = observer.observe(repo, when)
            assert outcome.observation is not None
            assert outcome.observation.confidence != CONFIDENCE_DIRECT

    def test_mandated_warning_text_is_exposed(self):
        assert "`direct` confidence " in NO_DIRECT_WARNING
        observer = CursorObserver(cursor_home=Path("/no/such/cursor-home"))
        assert NO_DIRECT_WARNING in observer.health()["detail"]

    def test_observer_is_versioned(self):
        observer = make_observer(Path("."))
        assert observer.vendor == "cursor"
        assert observer.vendor_release
        assert observer.adapter_version
