"""GitHub Copilot observer (FR-M35-02, FR-M35-03; F0 Workstream D task 19).

Two tiers of evidence:

1. **SCM/PR API** — where reachable, via the ``gh`` CLI (probed, never
   required — no credentials are needed for the tests and none are
   demanded of the user). PR-level attribution of Copilot-authored work
   (``copilot-swe-agent``, ``copilot-sweeper``, ``github-copilot[bot]``
   authors, ``copilot/`` head branches) is the agent's own SCM identity —
   confidence ``direct`` (FR-M35-03 vendor tag on the observation).
   A 200 response whose JSON lost the expected GitHub API shape is vendor
   drift: TelemetryFormatError, degrade to tier 2 with a visible warning
   (NFR-32). Auth/network failure makes the tier *unavailable* (silently
   skipped — that is reachability, not drift).
2. **In-editor inference** — workspace write bursts while no observed
   session and no trailers exist. Confidence ``inferred`` — the floor.

All probe subprocesses run with a scrubbed environment (SEC-27): no
MERIDIAN_* variable crosses into a child process, and the scrub is
audited. Zero model calls (FR-M36-07); pure stdlib.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..attribution._git import ensure_repo, run_git
from . import fsprobe
from .base import (
    CHAIN_FILESYSTEM,
    CHAIN_SCM_API,
    CONFIDENCE_DIRECT,
    CONFIDENCE_INFERRED,
    ChainOutcome,
    EvidenceTier,
    Observation,
    TelemetryFormatError,
    run_fallback_chain,
)
from .isolation import scrub_env

VENDOR = "copilot"
VENDOR_RELEASE = "2025-09"  # Copilot coding-agent platform release line
ADAPTER_VERSION = "1.0.0"

_DEFAULT_WINDOW_SECONDS = 30 * 60
_GH_TIMEOUT_SECONDS = 10

# Author identities GitHub uses for Copilot coding-agent / sweeper PRs.
COPILOT_AUTHOR_LOGINS = frozenset(
    {
        "copilot-swe-agent",
        "copilot-sweeper",
        "github-copilot[bot]",
        "github-copilot",
    }
)

# Runner: (argv, timeout_seconds) -> (returncode, stdout, stderr). Injected
# in tests so the whole observer runs with NO gh binary and NO credentials;
# the default shells out to the real CLI with a scrubbed environment.
Runner = Callable[[list[str], float], tuple[int, str, str]]


def default_runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
    """Run one probe with a SEC-27-scrubbed environment (audited)."""
    env, _scrubbed = scrub_env()
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return 127, "", "executable not found"
    except subprocess.TimeoutExpired:
        return 124, "", "probe timed out"
    return result.returncode, result.stdout, result.stderr


def github_repo_slug(workspace: Path, runner: Runner = default_runner) -> str | None:
    """owner/repo for the workspace's origin remote, or None.

    Reads `git remote get-url origin` (local, no network) and parses both
    https and ssh forms.
    """
    try:
        repo = ensure_repo(workspace)
        url = run_git(repo, "remote", "get-url", "origin").strip()
    except Exception:  # noqa: BLE001 - no repo / no remote: tier unavailable
        return None
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if url.startswith(prefix):
            slug = url[len(prefix):]
            break
    else:
        return None
    slug = slug.removesuffix(".git").strip("/")
    parts = slug.split("/")
    if len(parts) == 2 and all(parts):
        return "/".join(parts)
    return None


def is_copilot_pr(pull: dict[str, Any]) -> bool:
    """Recorded-shape GitHub API pull object -> Copilot-authored?"""
    user = pull.get("user")
    login = str((user or {}).get("login", "")).lower()
    if login in COPILOT_AUTHOR_LOGINS:
        return True
    if "copilot" in login and (user or {}).get("type") == "Bot":
        return True
    head_ref = str(((pull.get("head") or {}).get("ref")) or "").lower()
    if head_ref.startswith("copilot/"):
        return True
    title = str(pull.get("title") or "").lower()
    return title.startswith("copilot:") or title.startswith("copilot ")


class CopilotObserver:
    vendor = VENDOR
    vendor_release = VENDOR_RELEASE
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        runner: Runner = default_runner,
        gh_path: str | None = None,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._runner = runner
        # Probe lazily so tests (and machines) without gh pay nothing. An
        # empty string forces "unavailable" (test seam); None probes PATH.
        self._gh_path = gh_path if gh_path is not None else shutil.which("gh")
        self._window = window_seconds

    # -- evidence tiers ------------------------------------------------------

    def evidence_tiers(self) -> list[EvidenceTier]:
        return [
            EvidenceTier(CHAIN_SCM_API, CONFIDENCE_DIRECT, self._scan_scm_api),
            EvidenceTier(CHAIN_FILESYSTEM, CONFIDENCE_INFERRED, self._scan_workspace),
        ]

    def observe(self, workspace: Path, now: datetime) -> ChainOutcome:
        return run_fallback_chain(self.vendor, self.evidence_tiers(), workspace, now)

    def health(self) -> dict[str, Any]:
        if self._gh_path is None:
            return {"detail": "gh CLI not on PATH — SCM/PR tier unavailable; using workspace inference"}
        return {"detail": f"gh CLI: {self._gh_path}"}

    # -- tier 1: SCM/PR API ------------------------------------------------------

    def _scan_scm_api(self, workspace: Path, now: datetime) -> Observation | None:
        if not self._gh_path:
            return None  # tier unavailable, not drift
        slug = github_repo_slug(workspace)
        if slug is None:
            return None
        code, stdout, stderr = self._runner(
            [
                self._gh_path,
                "api",
                f"repos/{slug}/pulls",
                "--method",
                "GET",
                "-F",
                "state=all",
                "-F",
                "per_page=100",
            ],
            _GH_TIMEOUT_SECONDS,
        )
        if code != 0:
            # Unreachable / unauthenticated: availability, not drift.
            return None
        try:
            pulls = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise TelemetryFormatError(
                f"gh api returned non-JSON ({error})"
            ) from error
        if not isinstance(pulls, list):
            raise TelemetryFormatError(
                f"gh api response shape changed: expected a list, got "
                f"{type(pulls).__name__}"
            )
        window = _parse_window(pulls, now, self._window)
        if window is None:
            return None
        first, count = window
        return Observation(
            vendor=self.vendor,
            session_id=f"pr:{slug}#{first.get('number', '?')}",
            confidence=CONFIDENCE_DIRECT,
            source=CHAIN_SCM_API,
            detail=(
                f"{count} Copilot-authored PR(s) on {slug} in the last "
                f"{int(self._window)}s (author "
                f"{(first.get('user') or {}).get('login', '?')!r})"
            ),
            started_at=str(first.get("created_at") or now.isoformat()),
            workspace=str(workspace),
            agent_id="copilot",
        )

    # -- tier 2: in-editor inference ------------------------------------------------

    def _scan_workspace(self, workspace: Path, now: datetime) -> Observation | None:
        burst = fsprobe.recent_writes(workspace, now, self._window)
        if burst is None:
            return None
        return Observation(
            vendor=self.vendor,
            session_id=f"fs:{int(burst.latest_mtime)}",
            confidence=CONFIDENCE_INFERRED,
            source=CHAIN_FILESYSTEM,
            detail=(
                f"{burst.file_count} file(s) written in the last "
                f"{int(self._window)}s with no observed session and no "
                "trailers — in-editor Copilot activity is inferred, not proven"
            ),
            started_at=now.isoformat(),
            workspace=str(workspace),
            agent_id="copilot",
        )


def _parse_window(
    pulls: list[dict[str, Any]], now: datetime, window_seconds: float
) -> tuple[dict[str, Any], int] | None:
    """Copilot-authored PRs within the window, newest first."""
    if not pulls:
        return None
    first = pulls[0]
    if not isinstance(first, dict) or "user" not in first or "number" not in first:
        raise TelemetryFormatError(
            "gh api pull objects lost expected fields (user/number) — "
            "GitHub API shape changed"
        )
    cutoff = now.timestamp() - window_seconds
    in_window = []
    for pull in pulls:
        if not isinstance(pull, dict):
            raise TelemetryFormatError("gh api pull entry is not an object")
        stamp = str(pull.get("updated_at") or pull.get("created_at") or "")
        try:
            activity = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            raise TelemetryFormatError(
                f"gh api pull timestamp unparsable: {stamp!r}"
            ) from None
        if activity < cutoff:
            continue
        if is_copilot_pr(pull):
            in_window.append(pull)
    if not in_window:
        return None
    return in_window[0], len(in_window)
