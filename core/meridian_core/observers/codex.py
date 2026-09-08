"""Codex observer (FR-M35-02, FR-M35-08, D20; F1 Workstream G task 30).

Codex (OpenAI's Codex CLI) lands at `inferred` confidence as its floor,
`telemetry` at best — no credentialess first-party telemetry surface is
parseable by Meridian (D20). Two tiers of evidence, in preference order:

1. **Git trailers** — ``Co-Authored-By: Codex <codex@openai.com>`` in
   commit messages, parsed through the single shared trailer semantics of
   ``trailers.py``. Confidence ``telemetry`` — evidence the agent left
   behind. A trailer tier failure degrades to the filesystem tier WITH a
   visible warning (NFR-32), never silence.
2. **Filesystem inference** — a recent Codex CLI session rollout file
   (``~/.codex/sessions/**/*.jsonl``) written within the observation
   window. Confidence ``inferred`` — the floor. Only recency is evidence;
   the rollout file's *content* is never parsed, so a Codex format change
   cannot produce a fabricated session and there is no parse to drift.

`direct` is NEVER claimed: Meridian does not host the Codex session and
Codex publishes no local OTel export, so the honest ceiling is
`telemetry`. See ``NO_DIRECT_WARNING`` surfaced via ``health()``.

Process detection (``codex`` on the process table) is handled by the
session monitor (X-29), not here. Zero model calls (FR-M36-07); pure
stdlib + the shared git plumbing and trailer parser. SEC-27: no
credentials, no ledger imports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .. import trailers as trailers_mod
from ..attribution._git import ensure_repo, run_git
from .base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CONFIDENCE_INFERRED,
    CONFIDENCE_TELEMETRY,
    ChainOutcome,
    EvidenceTier,
    Observation,
    run_fallback_chain,
)

VENDOR = "codex"
VENDOR_RELEASE = "0.3"  # Codex CLI release line this adapter targets
ADAPTER_VERSION = "1.0.0"

_DEFAULT_WINDOW_SECONDS = 30 * 60
_CODEX_HOME = Path.home() / ".codex"

# The UI-boundary rule (D20): this observer never claims `direct`.
NO_DIRECT_WARNING = (
    "Codex is observed without first-party telemetry: `direct` confidence "
    "is not available for Codex. Meridian uses Co-Authored-By trailers and "
    "session-file inference (telemetry at best, inferred otherwise)."
)

# Bounded scan of the sessions tree (NFR-29): rollout files are few, but a
# long-lived home must not grow the probe without limit.
_MAX_SESSION_FILES = 5000


class CodexObserver:
    vendor = VENDOR
    vendor_release = VENDOR_RELEASE
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        codex_home: Path | None = None,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._codex_home = codex_home or _CODEX_HOME
        self._window = window_seconds

    # -- evidence tiers ------------------------------------------------------

    def evidence_tiers(self) -> list[EvidenceTier]:
        return [
            EvidenceTier(CHAIN_GIT_TRAILERS, CONFIDENCE_TELEMETRY, self._scan_trailers),
            EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, self._scan_filesystem),
        ]

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome:
        return run_fallback_chain(self.vendor, self.evidence_tiers(), workspace, now)

    def health(self) -> dict[str, Any]:
        if not self._codex_home.is_dir():
            return {
                "detail": (
                    f"Codex home {self._codex_home} not present — "
                    f"{NO_DIRECT_WARNING}"
                )
            }
        return {"detail": f"Codex home: {self._codex_home}"}

    # -- tier 1: git trailers ---------------------------------------------------

    def _scan_trailers(self, workspace: Path, now: datetime) -> Observation | None:
        try:
            repo = ensure_repo(workspace)
        except Exception:  # noqa: BLE001 - not a git repo: tier unavailable
            return None
        since = datetime.fromtimestamp(now.timestamp() - self._window, tz=now.tzinfo)
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
            # Single ownership of trailer semantics: trailers.py.
            if any(
                attribution["vendor"] == "codex"
                for attribution in trailers_mod.parse_attributions(body)
            ):
                hits.append((commit.strip(), authored.strip()))
        if not hits:
            return None
        first_commit, first_authored = hits[-1]  # git log is newest-first
        return Observation(
            vendor=self.vendor,
            session_id=f"git:{first_commit[:12]}",
            confidence=CONFIDENCE_TELEMETRY,
            source=CHAIN_GIT_TRAILERS,
            detail=(
                f"{len(hits)} commit(s) carry Codex trailers "
                "('Co-Authored-By: Codex <codex@openai.com>')"
            ),
            started_at=first_authored,
            workspace=str(repo),
            agent_id="codex",
        )

    # -- tier 2: session-file inference --------------------------------------------

    def _scan_filesystem(self, workspace: Path, now: datetime) -> Observation | None:
        session = self._recent_session_file(now)
        if session is None:
            return None
        mtime, path = session
        # The rollout filename is the readable session id ('rollout-...');
        # the content is deliberately never parsed (inference, not telemetry).
        session_id = path.stem.removeprefix("rollout-") or path.stem
        return Observation(
            vendor=self.vendor,
            session_id=f"fs:{session_id}",
            confidence=CONFIDENCE_INFERRED,
            source=CHAIN_FILESYSTEM,
            detail=(
                f"recent Codex session rollout ({path.name}) written in the "
                f"last {int(self._window)}s under {self._codex_home / 'sessions'} "
                "with no trailer evidence — the session file exists and is "
                "fresh; its content is not parsed"
            ),
            started_at=now.isoformat(),
            workspace=str(workspace),
            agent_id="codex",
        )

    def _recent_session_file(self, now: datetime) -> tuple[float, Path] | None:
        sessions = self._codex_home / "sessions"
        if not sessions.is_dir():
            return None
        cutoff = now.timestamp() - self._window
        newest: tuple[float, Path] | None = None
        scanned = 0
        for path in sorted(sessions.rglob("*.jsonl")):
            scanned += 1
            if scanned > _MAX_SESSION_FILES:
                break
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            if newest is None or mtime > newest[0]:
                newest = (mtime, path)
        return newest
