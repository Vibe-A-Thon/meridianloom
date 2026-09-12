"""Claude Code observer (FR-M35-02, FR-M35-08; F0 Workstream D task 18).

Three tiers of evidence, in preference order:

1. **OTel export** — OTLP JSON files the user points Meridian at (env
   ``MERIDIAN_CLAUDE_OTEL_DIR``); spans whose resource carries
   ``service.name: claude-code`` (or a ``session.id`` attribute).
   Confidence ``direct`` — the agent's own telemetry stream identified the
   session. This is the ONLY way local Claude Code reaches ``direct``:
   Meridian does not host the session in F0 (no ACP), so without OTel the
   UI must say so rather than overclaim.
2. **Git trailers** — ``Co-Authored-By: Claude <noreply@anthropic.com>``
   and ``Generated with Claude Code`` in commit messages. Confidence
   ``telemetry``.
3. **Filesystem inference** — recent Claude Code session transcripts
   (``~/.claude/projects/**.jsonl``) or CLAUDE.md-adjacent workspace write
   bursts. Confidence ``inferred`` — the floor, never silence.

A format change in the OTel export raises TelemetryFormatError and the
framework degrades to trailers WITH a visible warning (NFR-32).

Zero model calls (FR-M36-07); pure stdlib + the attribution git plumbing.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import trailers as trailers_mod
from ..attribution._git import ensure_repo, run_git
from . import fsprobe, otel
from .base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CHAIN_OTEL,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    EvidenceTier,
    Observation,
    ChainOutcome,
    run_fallback_chain,
)

VENDOR = "claude-code"
VENDOR_RELEASE = "1.0"  # Claude Code CLI release line this adapter targets
ADAPTER_VERSION = "1.0.0"

OTEL_DIR_ENV = "MERIDIAN_CLAUDE_OTEL_DIR"

# The exact UI-boundary text the spec mandates: local Claude Code without
# OTel must NOT claim `direct` — the UI shows this instead of overclaiming.
NO_OTEL_DIRECT_WARNING = (
    "Local Claude Code is observed without OpenTelemetry: `direct` confidence "
    "is not available. Enable Claude Code's OTel export for direct "
    "observation; until then Meridian uses Co-Authored-By trailers and "
    "filesystem inference (telemetry at best)."
)

TRAILER_COAUTHORED = "Co-Authored-By: Claude <noreply@anthropic.com>"
TRAILER_GENERATED = "Generated with Claude Code"

_DEFAULT_WINDOW_SECONDS = 30 * 60
_CLAUDE_HOME = Path.home() / ".claude"
_SESSION_ID_RE = re.compile(r'"sessionId"\s*:\s*"([^"]+)"')


class ClaudeCodeObserver:
    vendor = VENDOR
    vendor_release = VENDOR_RELEASE
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        otel_dir: Path | str | None = None,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        env: dict[str, str] | None = None,
        claude_home: Path | None = None,
    ) -> None:
        env = env if env is not None else os.environ
        self._otel_dir = Path(otel_dir) if otel_dir else None
        if self._otel_dir is None and env.get(OTEL_DIR_ENV):
            self._otel_dir = Path(env[OTEL_DIR_ENV])
        self._window = window_seconds
        self._claude_home = claude_home or _CLAUDE_HOME

    # -- evidence tiers ------------------------------------------------------

    def evidence_tiers(self) -> list[EvidenceTier]:
        return [
            EvidenceTier(CHAIN_OTEL, CONFIDENCE_DIRECT, self._scan_otel),
            EvidenceTier(CHAIN_GIT_TRAILERS, CONFIDENCE_INFERRED, self._scan_trailers),
            EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, self._scan_filesystem),
        ]

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome:
        return run_fallback_chain(self.vendor, self.evidence_tiers(), workspace, now)

    def health(self) -> dict[str, Any]:
        if self._otel_dir is None:
            return {"detail": f"OTel export not configured — {NO_OTEL_DIRECT_WARNING}"}
        return {"detail": f"OTel export dir: {self._otel_dir}"}

    # -- tier 1: OTel export ---------------------------------------------------

    def _scan_otel(self, workspace: Path, now: datetime) -> Observation | None:
        if self._otel_dir is None:
            return None  # tier unavailable, not drift
        spans = otel.export_dir_spans(self._otel_dir)
        claude = [s for s in spans if self._is_claude_span(s)]
        if not claude:
            return None
        cutoff = now.timestamp() - self._window
        recent = [
            s
            for s in claude
            if datetime.fromisoformat(s.started_at).timestamp() >= cutoff
        ]
        if not recent:
            return None
        session_id = (
            self._first_attr(recent, "session.id")
            or self._first_resource_attr(recent, "session.id")
            or (f"trace:{recent[0].trace_id}" if recent[0].trace_id else None)
        )
        started = min(s.started_at for s in recent)
        return Observation(
            vendor=self.vendor,
            session_id=session_id or "claude-otel-unknown",
            confidence=CONFIDENCE_DIRECT,
            source=CHAIN_OTEL,
            detail=(
                f"OTel export: {len(recent)} Claude Code span(s) in the last "
                f"{int(self._window)}s (service.name=claude-code)"
            ),
            started_at=started,
            workspace=str(workspace),
            agent_id="claude",
        )

    @staticmethod
    def _is_claude_span(span: otel.Span) -> bool:
        service = str(span.resource_attributes.get("service.name", "")).lower()
        if "claude" in service:
            return True
        # Some export configurations only carry a session.id attribute.
        return "session.id" in span.attributes or "session.id" in span.resource_attributes

    @staticmethod
    def _first_attr(spans: list[otel.Span], key: str) -> str | None:
        for span in spans:
            value = span.attributes.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _first_resource_attr(spans: list[otel.Span], key: str) -> str | None:
        for span in spans:
            value = span.resource_attributes.get(key)
            if value:
                return str(value)
        return None

    # -- tier 2: git trailers ---------------------------------------------------

    def _scan_trailers(self, workspace: Path, now: datetime) -> Observation | None:
        try:
            repo = ensure_repo(workspace)
        except Exception:  # noqa: BLE001 - not a git repo: tier unavailable
            return None
        since = datetime.fromtimestamp(now.timestamp() - self._window, tz=now.tzinfo)
        # %x1f field-separates, %x1e record-separates; body is the last field.
        fmt = "%H%x1f%cI%x1f%B%x1e"
        try:
            log = run_git(repo, "log", f"--since={since.isoformat()}", f"--format={fmt}")
        except Exception:  # noqa: BLE001 - git failure: no trailer evidence
            return None
        hits: list[tuple[str, str]] = []  # (commit, authored ISO)
        for record in log.split("\x1e"):
            record = record.strip("\n")
            if not record.strip():
                continue
            fields = record.split("\x1f", 2)
            if len(fields) < 3:
                continue
            commit, authored, body = fields
            # Single ownership of trailer semantics lives in trailers.py
            # (task 24): the Co-Authored-By evidence goes through the shared
            # parser. The "Generated with Claude Code" line is free text, not
            # a Key: value trailer, so it stays a substring check.
            mentions_claude = TRAILER_GENERATED in body or any(
                attribution["vendor"] == "claude"
                for attribution in trailers_mod.parse_attributions(body)
            )
            if mentions_claude:
                hits.append((commit.strip(), authored.strip()))
        if not hits:
            return None
        first_commit, first_authored = hits[-1]  # git log is newest-first
        return Observation(
            vendor=self.vendor,
            session_id=f"git:{first_commit[:12]}",
            # D55: a git trailer is text anyone with commit access can
            # type. `telemetry` names the agent's own instrumented output,
            # and a commit message is not that — docs/SECURITY-AND-DATA.md
            # §6 already tells customers the trailer "is a pointer, not a
            # proof". Capped at `inferred` so the confidence claim matches
            # what the evidence can carry. Nothing is lost: `source` still
            # says CHAIN_GIT_TRAILERS, so a consumer can tell a trailer from
            # a filesystem heuristic.
            confidence=CONFIDENCE_INFERRED,
            source=CHAIN_GIT_TRAILERS,
            detail=(
                f"{len(hits)} commit(s) carry Claude Code trailers "
                f"({TRAILER_COAUTHORED!r} / {TRAILER_GENERATED!r})"
            ),
            started_at=first_authored,
            workspace=str(repo),
            agent_id="claude",
        )

    # -- tier 3: filesystem inference -------------------------------------------

    def _scan_filesystem(self, workspace: Path, now: datetime) -> Observation | None:
        transcript_session = self._recent_transcript_session(now)
        burst = fsprobe.recent_writes(workspace, now, self._window)
        if transcript_session is not None:
            return Observation(
                vendor=self.vendor,
                session_id=transcript_session,
                confidence=CONFIDENCE_INFERRED,
                source=CHAIN_FILESYSTEM,
                detail="recent Claude Code session transcript under ~/.claude/projects",
                started_at=now.isoformat(),
                workspace=str(workspace),
                agent_id="claude",
            )
        claude_md = Path(workspace) / "CLAUDE.md"
        if claude_md.is_file() and burst is not None:
            return Observation(
                vendor=self.vendor,
                session_id=f"fs:{int(burst.latest_mtime)}",
                confidence=CONFIDENCE_INFERRED,
                source=CHAIN_FILESYSTEM,
                detail=(
                    f"CLAUDE.md present; {burst.file_count} file(s) written in the "
                    "last "
                    f"{int(self._window)}s with no stronger evidence"
                ),
                started_at=now.isoformat(),
                workspace=str(workspace),
                agent_id="claude",
            )
        return None

    def _recent_transcript_session(self, now: datetime) -> str | None:
        projects = self._claude_home / "projects"
        if not projects.is_dir():
            return None
        cutoff = now.timestamp() - self._window
        for path in sorted(projects.rglob("*.jsonl")):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:8192]
            except OSError:
                continue
            match = _SESSION_ID_RE.search(head)
            if match:
                return match.group(1)
        return None
