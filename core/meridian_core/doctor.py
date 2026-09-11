"""``meridian doctor`` check registry (FR-M30-01).

Each check is a pure function ``(params, context) -> DoctorCheck`` returning
the generated ``bus_types.DoctorCheck`` shape: ``{id, name, status, detail,
remediation?}`` with status ``pass`` | ``warn`` | ``fail``. Checks for
subsystems that do not exist yet (ledger, observers, trailer hook installer)
report ``warn`` with a not-installed detail and a concrete remediation rather
than crashing — doctor is the tool a user runs when something is *wrong*, so
no check may raise out of :func:`run_doctor`.

The registry is deliberately a plain ordered list: adding a check is adding
one entry, and the extension renders whatever the sidecar returns.

Host-side checks (the OS keychain via VS Code SecretStorage, the interpreter
resolution chain) live in the extension (extension/src/doctor.ts); this
module covers everything the sidecar can see for itself. A check never makes
a network or model call (FR-M36-07).
"""

from __future__ import annotations

from .gitcmd import GitTimeout, run_git_command

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bus_types

MIN_PYTHON_VERSION = (3, 11)

# Marker the trailer hook installer writes into the commit-msg hook it
# manages — single ownership lives in hooks.py (FR-M36-03, F0 Workstream E).
from .hooks import HOOK_MARKER


class UnknownCheckError(ValueError):
    """params.checks named an id that is not in the registry."""

    def __init__(self, unknown: list[str]) -> None:
        super().__init__(
            f"unknown doctor check id(s): {', '.join(sorted(unknown))}"
        )
        self.unknown = sorted(unknown)


@dataclass(frozen=True)
class DoctorContext:
    """Everything a check may need beyond params.

    The probes for not-yet-built subsystems default to None, which is exactly
    the "not installed — how to fix" path; Workstreams B/D/E will wire real
    probes in without changing the registry contract.
    """

    started_at: float
    # FR-M10-04: returns True when the ledger signing key exists in the OS
    # keychain. None until the ledger lands (Workstream B).
    signing_key_present: Callable[[], bool] | None = None
    # FR-M10-09: returns (ok, detail) from a chain verification run. None
    # until the ledger lands (Workstream B).
    ledger_verifier: Callable[[], tuple[bool, str]] | None = None
    # FR-M35-08: returns per-observer health dicts {name, status, detail}.
    # None until the observer framework lands (Workstream D).
    observer_health: Callable[[], list[dict[str, str]]] | None = None


@dataclass(frozen=True)
class CheckSpec:
    id: str
    name: str
    run: Callable[[dict[str, Any], DoctorContext], bus_types.DoctorCheck]


# Display names per check id, kept in one place so the check functions and
# the registry can never disagree.
_NAMES = {
    "interpreter": "Python interpreter",
    "sidecar": "Meridian Core sidecar",
    "signing-key": "Ledger signing key",
    "ledger": "Ledger integrity",
    "git-hooks": "Git provenance hooks",
    "observers": "Observer health",
}


def _check(
    check_id: str, status: str, detail: str, remediation: str | None = None
) -> bus_types.DoctorCheck:
    result: bus_types.DoctorCheck = {
        "id": check_id,
        "name": _NAMES[check_id],
        "status": status,  # type: ignore[typeddict-item]
        "detail": detail,
    }
    if remediation is not None:
        result["remediation"] = remediation
    return result


# Separated for tests: monkeypatching this proves the fail paths without a
# second interpreter on the machine.
def _interpreter_info() -> tuple[str, tuple[int, int, int]]:
    return sys.executable, tuple(sys.version_info[:3])  # type: ignore[return-value]


def _check_interpreter(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    executable, version = _interpreter_info()
    version_text = ".".join(str(part) for part in version)
    if version < MIN_PYTHON_VERSION:
        return _check(
            "interpreter",
            "fail",
            f"Python {version_text} at {executable or '(unknown)'} is too old",
            f"Meridian Core requires Python >= {'.'.join(map(str, MIN_PYTHON_VERSION))}. "
            "Install it and point meridian.python.interpreterPath at it.",
        )
    if not executable or not Path(executable).exists():
        return _check(
            "interpreter",
            "fail",
            f"the running interpreter path '{executable or '(empty)'} does not exist",
            "Set meridian.python.interpreterPath to a real Python 3.11+ executable "
            "and reload the window.",
        )
    return _check(
        "interpreter", "pass", f"Python {version_text} at {executable}"
    )


def _check_sidecar(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    # Reaching this check at all proves the framed-RPC round trip works; the
    # interesting facts are which build answered and for how long.
    uptime = time.monotonic() - context.started_at
    return _check(
        "sidecar",
        "pass",
        f"sidecar responding (pid {os.getpid()}, protocol "
        f"v{bus_types.PROTOCOL_VERSION}, uptime {uptime:.1f}s)",
    )


def _check_signing_key(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    if context.signing_key_present is None:
        return _check(
            "signing-key",
            "warn",
            "ledger signing key not provisioned — the ledger is not initialised yet",
            "The extension host provisions the 32-byte Ed25519 seed from "
            "SecretStorage over the stdio handshake (FR-M10-04, SEC-06); the "
            "ledger opens on the first ledger RPC once the handshake carries "
            "workspaceDir.",
        )
    if context.signing_key_present():
        return _check("signing-key", "pass", "ledger signing key present in the OS keychain")
    return _check(
        "signing-key",
        "fail",
        "ledger exists but its signing key is missing from the OS keychain",
        "The ledger cannot sign tree heads without its key. On Linux ensure a "
        "keyring backend (gnome-keyring or KWallet via libsecret) is running, "
        "then reload the window so the key is re-provisioned.",
    )


def _check_ledger(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    if context.ledger_verifier is None:
        return _check(
            "ledger",
            "warn",
            "ledger not initialised — hash-chain verification is not available yet",
            "The ledger opens on the first ledger RPC once the handshake "
            "carries workspaceDir (FR-M10-01); doctor verifies the chain "
            "here and names the first divergent sequence (FR-M10-09). "
            "Nothing to fix.",
        )
    ok, detail = context.ledger_verifier()
    if ok:
        return _check("ledger", "pass", detail)
    return _check(
        "ledger",
        "fail",
        detail,
        "Export an audit bundle before any repair, then re-run chain "
        "verification; do not delete ledger files by hand.",
    )


def _hooks_dir(workspace: Path) -> Path | None:
    """Resolve the hooks dir the way the installer does.

    ``git rev-parse --git-path hooks`` honours ``core.hooksPath`` at every
    config level and linked-worktree gitdirs. When git cannot answer (not a
    real repository, e.g. the synthetic fixtures in tests) fall back to the
    plain ``.git`` layout, including the ``gitdir:`` pointer file that
    linked worktrees and submodules use.
    """
    try:

        # The doctor must never be the thing that hangs: it is what a user
        # runs precisely when something already is.
        result = run_git_command(workspace, "rev-parse", "--git-path", "hooks")
        if result.returncode == 0 and result.stdout.strip():
            path = Path(result.stdout.strip())
            return path if path.is_absolute() else (workspace / path).resolve()
    except (OSError, ValueError):
        pass
    dot_git = workspace / ".git"
    if dot_git.is_dir():
        return dot_git / "hooks"
    if dot_git.is_file():
        for line in dot_git.read_text(encoding="utf-8").splitlines():
            if line.startswith("gitdir:"):
                gitdir = Path(line.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (workspace / gitdir).resolve()
                return gitdir / "hooks"
    return None


def _check_git_hooks(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    workspace_raw = (params or {}).get("workspaceDir")
    if not workspace_raw:
        return _check(
            "git-hooks",
            "warn",
            "no workspace folder open; hook status not checked",
            "Open the workspace folder and re-run meridian.doctor.",
        )
    hooks_dir = _hooks_dir(Path(workspace_raw))
    if hooks_dir is None:
        return _check(
            "git-hooks",
            "warn",
            f"{workspace_raw} is not a git repository",
            "Meridian's provenance trailers live in git; open a git repository "
            "to use them.",
        )
    hook = hooks_dir / "commit-msg"
    if not hook.exists():
        return _check(
            "git-hooks",
            "warn",
            "commit-msg hook not installed (provenance trailers are opt-in)",
            "Install the trailer hook from the Flight Recorder screen once it "
            "ships (F0 Workstream E, FR-M36-03); it is removable in one action.",
        )
    content = hook.read_text(encoding="utf-8", errors="replace")
    if HOOK_MARKER in content:
        return _check("git-hooks", "pass", f"Meridian commit-msg hook installed at {hook}")
    return _check(
        "git-hooks",
        "warn",
        f"a commit-msg hook exists at {hook} but is not Meridian's",
        "Meridian leaves foreign hooks untouched; when installed via the UI it "
        "chains onto the existing hook rather than replacing it (FR-M36-03).",
    )


def _check_observers(
    params: dict[str, Any], context: DoctorContext
) -> bus_types.DoctorCheck:
    if context.observer_health is None:
        return _check(
            "observers",
            "warn",
            "no observers registered — external-agent observation is not built yet",
            "Observers land with F0 Workstream D (FR-M35-08): Claude Code via "
            "OTel or Co-Authored-By trailers, Copilot via the SCM/PR API, with "
            "git-and-filesystem inference as the floor (G3). Nothing to fix.",
        )
    health = context.observer_health()
    degraded = [o for o in health if o.get("status") not in ("ok", "pass")]
    if not degraded:
        names = ", ".join(o.get("name", "?") for o in health)
        return _check("observers", "pass", f"all observers healthy ({names})")
    summary = "; ".join(
        f"{o.get('name', '?')}: {o.get('status', '?')} — {o.get('detail', '')}"
        for o in degraded
    )
    return _check(
        "observers",
        "warn",
        f"degraded observation: {summary}",
        "Observation degrades, never goes silent (G3/NFR-32): the affected "
        "observer falls back to git-and-filesystem inference and the affected "
        "sessions are labelled inferred.",
    )


CHECKS: list[CheckSpec] = [
    CheckSpec("interpreter", _NAMES["interpreter"], _check_interpreter),
    CheckSpec("sidecar", _NAMES["sidecar"], _check_sidecar),
    CheckSpec("signing-key", _NAMES["signing-key"], _check_signing_key),
    CheckSpec("ledger", _NAMES["ledger"], _check_ledger),
    CheckSpec("git-hooks", _NAMES["git-hooks"], _check_git_hooks),
    CheckSpec("observers", _NAMES["observers"], _check_observers),
]

assert {spec.id for spec in CHECKS} == set(_NAMES)


def check_ids() -> list[str]:
    return [spec.id for spec in CHECKS]


def run_doctor(
    params: dict[str, Any] | None, context: DoctorContext
) -> bus_types.DoctorRunResult:
    """Run the registry (or a params-selected subset) and aggregate.

    A check that raises becomes a ``fail`` entry naming the exception — a
    broken diagnostic must be visible, never silent.
    """
    params = params or {}
    selected = params.get("checks")
    specs = CHECKS
    if selected is not None:
        known = {spec.id for spec in CHECKS}
        unknown = [check_id for check_id in selected if check_id not in known]
        if unknown:
            raise UnknownCheckError(unknown)
        wanted = set(selected)
        specs = [spec for spec in CHECKS if spec.id in wanted]
    checks: list[bus_types.DoctorCheck] = []
    for spec in specs:
        try:
            checks.append(spec.run(params, context))
        except Exception as error:  # noqa: BLE001 - doctor must not crash
            checks.append(
                _check(
                    spec.id,
                    "fail",
                    f"check crashed: {error}",
                    "This is a bug in doctor itself; please report it with this output.",
                )
            )
    if any(check["status"] == "fail" for check in checks):
        status = "fail"
    elif any(check["status"] == "warn" for check in checks):
        status = "warn"
    else:
        status = "pass"
    return {"status": status, "checks": checks}  # type: ignore[typeddict-item]
