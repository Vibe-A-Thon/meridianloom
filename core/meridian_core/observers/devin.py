"""Devin observer (FR-M35-02, FR-M35-08, D20; F1 Workstream G task 30).

Devin (Cognition) lands at `inferred` confidence as its floor, `telemetry`
at best — no credentialess first-party telemetry surface is parseable by
Meridian (D20). Devin's deterministic local surface is git history: Devin
authors commits through its GitHub bot identity. Two tiers of evidence:

1. **Git attribution** — commits in the window whose *author* is a Devin
   bot identity (``devin[bot]`` / ``devin-ai-integration[bot]`` —
   recognised by the ``[bot]`` marker so a human named Devin is never
   misattributed), or whose message carries a Devin ``Co-Authored-By``
   trailer (parsed through the single shared trailer semantics of
   ``trailers.py``). Confidence ``telemetry`` — evidence the agent left
   behind in git. A tier failure degrades WITH a visible warning
   (NFR-32), never silence.
2. **Filesystem inference** — a recent write inside a user-pointed Devin
   Desktop state directory (env ``MERIDIAN_DEVIN_STATE_DIR``). Confidence
   ``inferred`` — the floor. When the directory is not pointed at, the
   tier is simply unavailable: there is no documented credentialess local
   Devin state location to probe, and inventing one would fabricate
   detections. A bare workspace write burst is deliberately NOT Devin
   evidence — unlike in-editor assistants, an unattributed burst cannot
   honestly carry Devin's vendor tag.

`direct` is NEVER claimed: Devin Desktop speaks ACP, and an ACP session
hosted by Meridian would be the `direct` path (F1 hosted agents) — until
then the honest ceiling is `telemetry`. See ``NO_DIRECT_WARNING``
surfaced via ``health()``.

Process detection (``devin`` on the process table) is handled by the
session monitor (X-29), not here. Zero model calls (FR-M36-07); pure
stdlib + the shared git plumbing and trailer parser. SEC-27: no
credentials, no ledger imports.
"""

from __future__ import annotations

import os
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

VENDOR = "devin"
VENDOR_RELEASE = "2025.09"  # Devin platform / Devin Desktop release line
ADAPTER_VERSION = "1.0.0"

STATE_DIR_ENV = "MERIDIAN_DEVIN_STATE_DIR"
_DEFAULT_WINDOW_SECONDS = 30 * 60

# The UI-boundary rule (D20): this observer never claims `direct`.
NO_DIRECT_WARNING = (
    "Devin is observed without first-party telemetry: `direct` confidence "
    "requires an ACP session hosted by Meridian. Until then Meridian uses "
    "git attribution of Devin's bot identity (telemetry at best, inferred "
    "otherwise)."
)

# Bounded scan of the pointed-at state dir (NFR-29).
_MAX_STATE_FILES = 5000


def is_devin_author(name: str, email: str) -> bool:
    """Recorded git author identity -> Devin bot?

    The ``[bot]`` marker is required: it is what GitHub appends to app
    login names, and it is what keeps a human named Devin from being
    misattributed.
    """
    identity = f"{name} <{email}>".lower()
    return "[bot]" in identity and "devin" in identity


class DevinObserver:
    vendor = VENDOR
    vendor_release = VENDOR_RELEASE
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        state_dir: Path | str | None = None,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        env: dict[str, str] | None = None,
    ) -> None:
        env = env if env is not None else os.environ
        self._state_dir = Path(state_dir) if state_dir else None
        if self._state_dir is None and env.get(STATE_DIR_ENV):
            self._state_dir = Path(env[STATE_DIR_ENV])
        self._window = window_seconds

    # -- evidence tiers ------------------------------------------------------

    def evidence_tiers(self) -> list[EvidenceTier]:
        return [
            EvidenceTier(CHAIN_GIT_TRAILERS, CONFIDENCE_TELEMETRY, self._scan_git),
            EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, self._scan_filesystem),
        ]

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome:
        return run_fallback_chain(self.vendor, self.evidence_tiers(), workspace, now)

    def health(self) -> dict[str, Any]:
        if self._state_dir is None:
            return {
                "detail": (
                    f"Devin Desktop state dir not configured "
                    f"({STATE_DIR_ENV}) — {NO_DIRECT_WARNING}"
                )
            }
        return {"detail": f"Devin state dir: {self._state_dir}"}

    # -- tier 1: git attribution ------------------------------------------------

    def _scan_git(self, workspace: Path, now: datetime) -> Observation | None:
        try:
            repo = ensure_repo(workspace)
        except Exception:  # noqa: BLE001 - not a git repo: tier unavailable
            return None
        since = datetime.fromtimestamp(now.timestamp() - self._window, tz=now.tzinfo)
        # Author name+email ride alongside the body: Devin AUTHORS its
        # commits (the bot is the committer identity), it does not merely
        # co-author them.
        fmt = "%H%x1f%cI%x1f%an%x1f%ae%x1f%B%x1e"
        try:
            log = run_git(repo, "log", f"--since={since.isoformat()}", f"--format={fmt}")
        except Exception:  # noqa: BLE001 - git failure: no git evidence
            return None
        hits: list[tuple[str, str]] = []  # (commit, authored ISO)
        for record in log.split("\x1e"):
            record = record.strip("\n")
            if not record.strip():
                continue
            fields = record.split("\x1f", 4)
            if len(fields) < 5:
                continue
            commit, authored, author_name, author_email, body = fields
            authored_by_devin = is_devin_author(author_name, author_email)
            coauthored_by_devin = any(
                attribution["vendor"] == "devin"
                for attribution in trailers_mod.parse_attributions(body)
            )
            if authored_by_devin or coauthored_by_devin:
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
                f"{len(hits)} commit(s) authored by a Devin bot identity "
                "('devin-ai-integration[bot]') in the last "
                f"{int(self._window)}s"
            ),
            started_at=first_authored,
            workspace=str(repo),
            agent_id="devin",
        )

    # -- tier 2: state-dir inference ----------------------------------------------

    def _scan_filesystem(self, workspace: Path, now: datetime) -> Observation | None:
        if self._state_dir is None:
            return None  # tier unavailable, not drift
        newest = self._recent_state_write(now)
        if newest is None:
            return None
        mtime, rel = newest
        return Observation(
            vendor=self.vendor,
            session_id=f"fs:{int(mtime)}",
            confidence=CONFIDENCE_INFERRED,
            source=CHAIN_FILESYSTEM,
            detail=(
                f"recent write under the configured Devin state dir "
                f"({self._state_dir}: {rel}) in the last {int(self._window)}s "
                "with no git evidence — Devin Desktop activity is inferred, "
                "not proven"
            ),
            started_at=now.isoformat(),
            workspace=str(workspace),
            agent_id="devin",
        )

    def _recent_state_write(self, now: datetime) -> tuple[float, str] | None:
        root = self._state_dir
        if root is None or not root.is_dir():
            return None
        cutoff = now.timestamp() - self._window
        newest: tuple[float, str] | None = None
        scanned = 0
        for path in root.rglob("*"):
            scanned += 1
            if scanned > _MAX_STATE_FILES:
                break
            try:
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = path.name
            if newest is None or mtime > newest[0]:
                newest = (mtime, rel)
        return newest
