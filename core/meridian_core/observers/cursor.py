"""Cursor observer (FR-M35-02, FR-M35-08, D20; F1 Workstream G task 30).

Cursor lands at `inferred` confidence as its floor, `telemetry` at best —
there is no credentialess first-party telemetry surface Meridian can parse
(D20: first-class observers in F0 were Claude Code + Copilot only). Two
tiers of evidence, in preference order:

1. **Git trailers** — ``Co-Authored-By: Cursor <cursor@anysphere.inc>`` /
   ``<cursor@cursor.com>`` in commit messages, parsed through the single
   shared trailer semantics of ``trailers.py``. Confidence ``telemetry`` —
   evidence the agent left behind. A trailer tier failure degrades to the
   filesystem tier WITH a visible warning (NFR-32), never silence.
2. **Filesystem inference** — (a) a recent write inside the Cursor state
   home (``~/.cursor`` — chats/compose/worktrees state) within the
   observation window, or (b) a Cursor workspace marker (``.cursor/``,
   ``.cursorrules``) plus a write burst with no stronger evidence.
   Confidence ``inferred`` — the floor.

`direct` is NEVER claimed: Meridian does not host Cursor's session (no
ACP hosting of Cursor) and Cursor publishes no local OTel export, so the
honest ceiling is `telemetry`. See ``NO_DIRECT_WARNING`` surfaced via
``health()`` for the UI boundary.

Process detection (``cursor-agent`` on the process table) is handled by
the session monitor (X-29), not here. Zero model calls (FR-M36-07); pure
stdlib + the shared git plumbing and trailer parser. SEC-27: no
credentials, no ledger imports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .. import trailers as trailers_mod
from ..attribution._git import ensure_repo, run_git
from . import fsprobe
from .base import (
    CHAIN_FILESYSTEM,
    CHAIN_GIT_TRAILERS,
    CONFIDENCE_INFERRED,
    ChainOutcome,
    EvidenceTier,
    Observation,
    run_fallback_chain,
)

VENDOR = "cursor"
VENDOR_RELEASE = "2025.09"  # Cursor / Cursor Agent CLI release line targeted
ADAPTER_VERSION = "1.0.0"

_DEFAULT_WINDOW_SECONDS = 30 * 60
_CURSOR_HOME = Path.home() / ".cursor"

# The UI-boundary rule (D20): this observer never claims `direct`.
NO_DIRECT_WARNING = (
    "Cursor is observed without first-party telemetry: `direct` confidence "
    "is not available for Cursor. Meridian uses Co-Authored-By trailers and "
    "filesystem inference (telemetry at best, inferred otherwise)."
)


class CursorObserver:
    vendor = VENDOR
    vendor_release = VENDOR_RELEASE
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        cursor_home: Path | None = None,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._cursor_home = cursor_home or _CURSOR_HOME
        self._window = window_seconds

    # -- evidence tiers ------------------------------------------------------

    def evidence_tiers(self) -> list[EvidenceTier]:
        return [
            EvidenceTier(CHAIN_GIT_TRAILERS, CONFIDENCE_INFERRED, self._scan_trailers),
            EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, self._scan_filesystem),
        ]

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome:
        return run_fallback_chain(self.vendor, self.evidence_tiers(), workspace, now)

    def health(self) -> dict[str, Any]:
        if not self._cursor_home.is_dir():
            return {
                "detail": (
                    f"Cursor state home {self._cursor_home} not present — "
                    f"{NO_DIRECT_WARNING}"
                )
            }
        return {"detail": f"Cursor state home: {self._cursor_home}"}

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
                attribution["vendor"] == "cursor"
                for attribution in trailers_mod.parse_attributions(body)
            ):
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
                f"{len(hits)} commit(s) carry Cursor Co-Authored-By trailers "
                "('Cursor <cursor@anysphere.inc>' / 'Cursor <cursor@cursor.com>')"
            ),
            started_at=first_authored,
            workspace=str(repo),
            agent_id="cursor",
        )

    # -- tier 2: filesystem inference --------------------------------------------

    def _scan_filesystem(self, workspace: Path, now: datetime) -> Observation | None:
        state_hit = self._recent_state_write(now)
        if state_hit is not None:
            mtime, rel = state_hit
            return Observation(
                vendor=self.vendor,
                session_id=f"fs:{int(mtime)}",
                confidence=CONFIDENCE_INFERRED,
                source=CHAIN_FILESYSTEM,
                detail=(
                    f"recent write under the Cursor state home "
                    f"({self._cursor_home}: {rel}) in the last {int(self._window)}s "
                    "with no trailer evidence — Cursor activity is inferred, "
                    "not proven"
                ),
                started_at=now.isoformat(),
                workspace=str(workspace),
                agent_id="cursor",
            )
        # Workspace marker + write burst: the CLAUDE.md pattern from the
        # Claude observer — a Cursor rules file shows the workspace is
        # Cursor-driven, the burst shows recent agent-shaped activity.
        marker = self._workspace_marker(workspace)
        burst = fsprobe.recent_writes(workspace, now, self._window)
        if marker is not None and burst is not None:
            return Observation(
                vendor=self.vendor,
                session_id=f"fs:{int(burst.latest_mtime)}",
                confidence=CONFIDENCE_INFERRED,
                source=CHAIN_FILESYSTEM,
                detail=(
                    f"{marker} present; {burst.file_count} file(s) written in "
                    f"the last {int(self._window)}s with no stronger evidence"
                ),
                started_at=now.isoformat(),
                workspace=str(workspace),
                agent_id="cursor",
            )
        return None

    def _recent_state_write(self, now: datetime) -> tuple[float, str] | None:
        """Newest file under the Cursor state home within the window.

        Bounded walk — the probe must stay cheap (NFR-29) even in a large
        state home. Existence of the home alone is NOT evidence; only a
        write inside the observation window is.
        """
        home = self._cursor_home
        if not home.is_dir():
            return None
        cutoff = now.timestamp() - self._window
        newest: tuple[float, str] | None = None
        visited = 0
        for path in home.rglob("*"):
            visited += 1
            if visited > fsprobe._MAX_VISITED_DIRS * 10:  # files, not dirs
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
                rel = path.relative_to(home).as_posix()
            except ValueError:
                rel = path.name
            if newest is None or mtime > newest[0]:
                newest = (mtime, rel)
        return newest

    @staticmethod
    def _workspace_marker(workspace: Path) -> str | None:
        if (Path(workspace) / ".cursor").is_dir():
            return ".cursor/"
        if (Path(workspace) / ".cursorrules").is_file():
            return ".cursorrules"
        return None
