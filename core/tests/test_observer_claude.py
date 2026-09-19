"""Claude Code observer tests (FR-M35-02, FR-M35-08, NFR-32; task 18).

Three evidence tiers are proven against recorded-real shapes: the checked-in
OTLP export fixture (OTLP/HTTP JSON protobuf encoding, as produced by
opentelemetry-python's JsonEncoder — the shape Claude Code's OTel exporter
writes), git trailers in real fixture commits, and filesystem inference.

The UI-boundary rule is asserted exactly: without OTel, `direct` is never
claimed, and the mandated warning text is exposed for the UI.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meridian_core.observers.base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CHAIN_OTEL,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    CONFIDENCE_TELEMETRY,
)
from meridian_core.observers.claude import (
    NO_OTEL_DIRECT_WARNING,
    TRAILER_COAUTHORED,
    TRAILER_GENERATED,
    ClaudeCodeObserver,
)
from test_attribution import git

FIXTURE_EXPORT = Path(__file__).parent / "fixtures" / "otel" / "claude-export.json"

# The fixture's recent session span starts at 2025-09-20T12:00:00Z; the old
# session is ~110 minutes earlier, outside the default 30-minute window.
NOW = datetime(2025, 9, 20, 12, 10, tzinfo=timezone.utc)


def make_observer(tmp_path: Path, **kwargs) -> ClaudeCodeObserver:
    otel_dir = tmp_path / "otel"
    otel_dir.mkdir()
    (otel_dir / "export.json").write_text(
        FIXTURE_EXPORT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    kwargs.setdefault("claude_home", tmp_path / "no-such-claude-home")
    return ClaudeCodeObserver(otel_dir=otel_dir, **kwargs)


class TestOtelTier:
    def test_recorded_otlp_payload_yields_direct_session(self, tmp_path):
        observer = make_observer(tmp_path)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_DIRECT
        assert outcome.observation.source == CHAIN_OTEL
        assert outcome.observation.session_id == "session-abc-123"
        assert outcome.observation.started_at.startswith("2025-09-20T12:00:00")

    def test_old_session_outside_window_is_not_reported(self, tmp_path):
        observer = make_observer(tmp_path)
        # Only the old span remains inside a 3-hour-old window reference:
        # jump now past the recent session entirely.
        outcome = observer.observe(tmp_path, NOW + timedelta(hours=2))
        assert outcome.observation is None

    def test_non_claude_spans_are_ignored(self, tmp_path):
        observer = make_observer(tmp_path)
        outcome = observer.observe(tmp_path, NOW)
        # The unrelated-user-service span must not leak into the session.
        assert "http" not in outcome.observation.detail

    def test_format_change_degrades_to_trailers_with_warning(self, tmp_path, repo):
        observer = make_observer(tmp_path)
        # Vendor ships export schema v9: valid JSON, unrecognizable shape.
        export = tmp_path / "otel" / "export.json"
        export.write_text(json.dumps({"telemetry": {"schema": 9}}), encoding="utf-8")
        commit_with_trailers(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_OTEL
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_GIT_TRAILERS
        assert outcome.warnings and "NFR-32" in outcome.warnings[0]

    def test_malformed_json_is_format_change_not_silence(self, tmp_path, repo):
        observer = make_observer(tmp_path)
        (tmp_path / "otel" / "export.json").write_text("{ not json", encoding="utf-8")
        commit_with_trailers(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from == CHAIN_OTEL
        assert outcome.observation is not None
        assert outcome.warnings

    def test_missing_otel_dir_is_unavailable_not_drift(self, tmp_path, repo):
        observer = ClaudeCodeObserver(otel_dir=tmp_path / "nope")
        commit_with_trailers(repo)
        outcome = observer.observe(repo, NOW)
        assert outcome.degraded_from is None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED

    def test_ndjson_exports_are_parsed(self, tmp_path):
        otel_dir = tmp_path / "otel"
        otel_dir.mkdir()
        payload = json.loads(FIXTURE_EXPORT.read_text(encoding="utf-8"))
        with (otel_dir / "spans.jsonl").open("w", encoding="utf-8") as fh:
            for resource_span in payload["resourceSpans"]:
                fh.write(json.dumps({"resourceSpans": [resource_span]}) + "\n")
        observer = ClaudeCodeObserver(otel_dir=otel_dir)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation.confidence == CONFIDENCE_DIRECT
        assert outcome.observation.session_id == "session-abc-123"


def commit_with_trailers(repo: Path, when: int | None = None) -> None:
    when = when or int(NOW.timestamp()) - 120
    (repo / "src" / "agent.txt").write_text("agent wrote this\n", encoding="utf-8")
    git(repo, "add", ".")
    message = (
        "feat: agent change\n\n"
        f"{TRAILER_GENERATED}\n\n"
        f"{TRAILER_COAUTHORED}\n"
    )
    git(repo, "commit", "-m", message, date=when)


class TestTrailerTier:
    def test_coauthored_and_generated_trailers_yield_telemetry(self, repo):
        commit_with_trailers(repo)
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_GIT_TRAILERS
        assert outcome.observation.session_id.startswith("git:")

    def test_trailers_outside_window_are_not_evidence(self, repo):
        commit_with_trailers(repo, when=int(NOW.timestamp()) - 6 * 3600)
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None

    def test_plain_commits_are_not_evidence(self, repo):
        (repo / "src" / "human.txt").write_text("human work\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "human change")
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None


class TestFilesystemTier:
    def test_recent_transcript_yields_inferred(self, tmp_path):
        claude_home = tmp_path / "claudehome"
        session = claude_home / "projects" / "ws" / "session-transcript.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps({"sessionId": "transcript-session-9", "type": "summary"})
            + "\n",
            encoding="utf-8",
        )
        os.utime(session, (NOW.timestamp() - 60, NOW.timestamp() - 60))
        observer = ClaudeCodeObserver(env={}, claude_home=claude_home)
        outcome = observer.observe(tmp_path, NOW)
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.session_id == "transcript-session-9"

    def test_claude_md_plus_write_burst_yields_inferred(self, repo):
        (repo / "CLAUDE.md").write_text("# project notes\n", encoding="utf-8")
        (repo / "src" / "burst.txt").write_text("line\n" * 40, encoding="utf-8")
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, datetime.now(timezone.utc))
        assert outcome.observation is not None
        assert outcome.observation.confidence == CONFIDENCE_INFERRED
        assert outcome.observation.source == CHAIN_FILESYSTEM

    def test_no_evidence_anywhere_is_honest_none(self, repo):
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation is None


class TestUiBoundaryRule:
    def test_direct_is_never_claimed_without_otel(self, repo):
        # Without OTel the best available tier is trailers — telemetry.
        commit_with_trailers(repo)
        observer = ClaudeCodeObserver(env={}, claude_home=repo / "no-claude-home")
        outcome = observer.observe(repo, NOW)
        assert outcome.observation.confidence != CONFIDENCE_DIRECT

    def test_mandated_warning_text_is_exposed(self):
        assert "`direct` confidence " in NO_OTEL_DIRECT_WARNING
        assert "OpenTelemetry" in NO_OTEL_DIRECT_WARNING
        observer = ClaudeCodeObserver(env={})
        assert NO_OTEL_DIRECT_WARNING in observer.health()["detail"]

    def test_observer_is_versioned(self):
        observer = ClaudeCodeObserver(env={})
        assert observer.vendor == "claude-code"
        assert observer.vendor_release
        assert observer.adapter_version
