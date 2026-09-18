"""FR-M43-12…14 (N2 Workstream D task 19): the headless collector.

Meridian's evidence pipeline without the editor: collect external-agent
observations into the workspace ledger, export a portable signed evidence
bundle, drive subject erasure, and uninstall Meridian state — each path
documented and test-covered.

Paths (``<ws>`` = workspace root):

- ``collect``  — observe → exactly-once ingest (FR-M41-10) into
  ``<ws>/.meridian/ledger``. Creates the ledger on first use.
- ``export``   — recipient-specific portable bundle (FR-M43-06): chain
  bundle with ``schemaVersion``, workspace source identifiers, and the
  privacy section naming withheld (redaction-labelled) subjects. Optional
  opt-in ``sink`` posts a COPY to an observability endpoint; the local
  ledger remains the record of authority and is byte-identical afterwards
  (FR-M43-14).
- ``erase``    — subject erasure via the privacy lifecycle
  (``ledger/privacy.py``); erasure is itself a ledger entry.
- ``uninstall``— removes Meridian operational state under ``<ws>/.meridian``
  EXCEPT the evidence ledger, receipts and archive (the compliance
  record). Never touches git history or user source. Refuses while agent
  worktrees still exist under ``.meridian/worktrees`` — merge or remove
  them first; we do not silently discard possibly-unmerged agent work.
  Deletes the collector signing seed (secrets must not linger).

Signing seed resolution for headless operation: the extension host's
handshake seed stays authoritative in editor sessions; headless, the
collector uses ``MERIDIAN_LEDGER_SIGNING_SEED`` (hex) when set, else a
random seed created once at ``<ws>/.meridian/secrets/ledger-signing.seed``
(mode 0600, O_EXCL). When neither exists it falls back to an ephemeral
signer and SAYS so — tree-head signatures then only live for the process.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meridian_core.gitcmd import GitTimeout, run_git_command
from meridian_core.ingest import EventIngester, SourceEvent
from meridian_core.ledger import core as ledger_core
from meridian_core.ledger import keys as ledger_keys
from meridian_core.ledger import privacy as ledger_privacy
from meridian_core.observers import base as observer_base
from meridian_core.observers import claude as observer_claude
from meridian_core.observers import codex as observer_codex
from meridian_core.observers import copilot as observer_copilot
from meridian_core.observers import cursor as observer_cursor
from meridian_core.observers import devin as observer_devin
from meridian_core.observers import manager as observer_manager

MERIDIAN_DIR = ".meridian"
SEED_ENV = "MERIDIAN_LEDGER_SIGNING_SEED"
SEED_RELPATH = Path(MERIDIAN_DIR) / "secrets" / "ledger-signing.seed"
HEADLESS_SOURCE = "headless-collector"
EXPORT_RECIPIENT = "meridian-portable-export"

# Evidence that must survive uninstall (the compliance record).
PRESERVED_ON_UNINSTALL = ("ledger", "receipts", "archive")


class CollectorError(RuntimeError):
    """A headless operation refused or failed. Carries the requirement ID."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_bytes(workspace: Path, warnings: list[str]) -> bytes | None:
    env_seed = os.environ.get(SEED_ENV)
    if env_seed:
        try:
            return bytes.fromhex(env_seed.strip())
        except ValueError as exc:
            raise CollectorError(
                f"FR-M43-12: {SEED_ENV} is not hex-encoded: {exc}"
            )
    seed_path = workspace / SEED_RELPATH
    if seed_path.exists():
        return bytes.fromhex(seed_path.read_text(encoding="ascii").strip())
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed = os.urandom(32)
    fd = os.open(seed_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(seed.hex())
    warnings.append(
        f"created headless signing seed at {seed_path} (mode 0600); set"
        f" {SEED_ENV} to manage the key outside the workspace"
    )
    return seed


def open_collector_ledger(workspace: Path | str) -> tuple[ledger_core.Ledger, list[str]]:
    """Open (creating if needed) the workspace ledger for headless use."""
    root = Path(workspace)
    warnings: list[str] = []
    try:
        seed = _seed_bytes(root, warnings)
    except CollectorError:
        raise
    except OSError as exc:  # unreadable/unwritable seed — do not crash
        warnings.append(f"signing seed unavailable ({exc}); ephemeral signer")
        seed = None
    if seed is not None:
        provider: ledger_keys.SigningKeyProvider = (
            ledger_keys.ProvisionedSigningKeyProvider(seed)
        )
    else:
        provider = ledger_keys.EphemeralSigningKeyProvider()
        warnings.append(
            "ephemeral ledger signer: tree-head signatures from this run"
            " cannot be re-signed later"
        )
    ledger = ledger_core.Ledger(root / MERIDIAN_DIR / "ledger", provider)
    return ledger, warnings


def default_observer_manager() -> observer_manager.ObserverManager:
    """The same credential-free observer roster the sidecar runs (FR-M36)."""
    return observer_manager.ObserverManager(
        [
            observer_claude.ClaudeCodeObserver(),
            observer_copilot.CopilotObserver(),
            observer_cursor.CursorObserver(),
            observer_codex.CodexObserver(),
            observer_devin.DevinObserver(),
        ]
    )


def _observation_event(observation: observer_base.Observation, offset: int) -> SourceEvent:
    day = observation.started_at[:10].replace("-", "")
    return SourceEvent(
        key=f"{observation.vendor}:{observation.session_id}",
        offset=offset,
        body={
            "story_id": f"OBS-{observation.vendor}-{day}",
            "phase": "observe",
            "loop_id": HEADLESS_SOURCE,
            "loop_iteration": 1,
            "actor_id": observation.vendor,
            "actor_version": "observed",
            "actor_kind": "external",
            "policy_version": "headless",
            "action_type": "scan",
            "tool_calls": json.dumps(
                [
                    {
                        "sessionId": observation.session_id,
                        "confidence": observation.confidence,
                        "source": observation.source,
                        "detail": observation.detail,
                        "startedAt": observation.started_at,
                    }
                ]
            ),
        },
    )


def collect(
    workspace: Path | str,
    *,
    manager: observer_manager.ObserverManager | None = None,
) -> dict[str, Any]:
    """Observe external agents in ``workspace``; ingest exactly once.

    ``manager`` is injectable for tests; production uses the same
    credential-free roster the sidecar runs (``default_observer_manager``).
    """
    root = Path(workspace)
    if not root.is_dir():
        raise CollectorError(f"FR-M43-12: workspace {root} is not a directory")
    ledger, warnings = open_collector_ledger(root)
    try:
        manager = manager or default_observer_manager()
        observations = manager.observe(root)
        ingester = EventIngester(ledger, source=HEADLESS_SOURCE)
        events = [
            _observation_event(obs, offset)
            for offset, obs in enumerate(observations)
        ]
        result = ingester.ingest_batch(events) if events else None
        head = ledger.latest_tree_head()
        return {
            "observations": len(observations),
            "vendors": sorted({o.vendor for o in observations}),
            "ingest": result.to_dict() if result is not None else None,
            "treeHeadSeq": head["seq"] if head else None,
            "warnings": warnings,
        }
    finally:
        ledger.close()


def workspace_identity(workspace: Path | str) -> dict[str, Any]:
    """Source identifiers for exports (FR-M43-13): repository identity when
    the workspace is a git checkout, else a stable digest of the path —
    never absolute paths (portability must not leak machine layout)."""
    root = Path(workspace)
    identity: dict[str, Any] = {"kind": "directory", "name": root.name}
    try:
        toplevel_result = run_git_command(
            root,
            "rev-parse",
            "--show-toplevel",
            timeout=15,
        )
        if toplevel_result.returncode != 0:
            raise OSError(toplevel_result.stderr.strip())
        toplevel = toplevel_result.stdout.strip()
        remote = run_git_command(
            root,
            "config",
            "--get",
            "remote.origin.url",
            timeout=15,
        ).stdout.strip()
        identity.update(
            {
                "kind": "git",
                "repository": remote or None,
                "worktreeDigest": hashlib.sha256(
                    toplevel.encode("utf-8")
                ).hexdigest(),
            }
        )
    except (GitTimeout, OSError):
        identity["pathDigest"] = hashlib.sha256(
            str(root.resolve()).encode("utf-8")
        ).hexdigest()
    return identity


def export_portable(
    workspace: Path | str,
    out_dir: Path | str,
    *,
    sink: str | None = None,
    sink_timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Recipient-specific portable export (FR-M43-13).

    The bundle carries ``schemaVersion``, the workspace source identifiers,
    and the privacy section naming withheld subjects — redaction labels
    survive export. ``sink`` (opt-in) posts a copy of the export manifest
    to an observability endpoint; the local ledger is the record of
    authority and is not modified by sinking (FR-M43-14) — the tree head
    before and after must be identical.
    """
    root = Path(workspace)
    ledger, warnings = open_collector_ledger(root)
    try:
        controller = ledger_privacy.PrivacyController(ledger)
        exported = controller.export_for_recipient(EXPORT_RECIPIENT)
        # The authority check brackets the SINK only: building the export
        # bundle may legitimately emit a new signed tree head (FR-M10-04
        # cadence); what must never change is the ledger as a result of
        # POSTing a copy elsewhere (FR-M43-14).
        head_before = ledger.latest_tree_head()
        before_key = (head_before or {}).get("root_hash")
        bundle = exported["bundle"]
        manifest = {
            "schemaVersion": bundle.get("schemaVersion"),
            "exportedAt": utc_now(),
            "source": workspace_identity(root),
            "recipient": EXPORT_RECIPIENT,
            "withheldSubjects": exported["withheldSubjects"],
            "consentedSubjects": exported["consentedSubjects"],
            "recordOfAuthority": "local-ledger",
            "note": (
                "This export is a copy. The workspace ledger remains the"
                " record of authority; sinking it to an observability"
                " system does not cede that role (FR-M43-14)."
            ),
        }
        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        (destination / "bundle.json").write_text(
            json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8"
        )
        sink_status: dict[str, Any] = {"sunk": False}
        if sink:
            payload = json.dumps({"manifest": manifest}).encode("utf-8")
            request = urllib.request.Request(
                sink,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=sink_timeout_s) as resp:
                sink_status = {"sunk": True, "status": resp.status}
        head_after = ledger.latest_tree_head()
        after_key = (head_after or {}).get("root_hash")
        if before_key != after_key:
            raise CollectorError(
                "FR-M43-14: sinking modified the record of authority"
                " (tree head changed) — refusing to report success"
            )
        return {
            "outDir": str(destination),
            "manifest": str(destination / "manifest.json"),
            "bundle": str(destination / "bundle.json"),
            "withheldSubjects": exported["withheldSubjects"],
            "sink": sink_status,
            "authorityUnchanged": before_key == after_key,
            "warnings": warnings,
        }
    finally:
        ledger.close()


def erase_subject(workspace: Path | str, subject_id: str) -> dict[str, Any]:
    """Erase one subject via the privacy lifecycle (FR-M43-07/08)."""
    root = Path(workspace)
    ledger, warnings = open_collector_ledger(root)
    try:
        controller = ledger_privacy.PrivacyController(ledger)
        result = controller.erase_subject(
            subject_id, reason="headless erasure request", actor=HEADLESS_SOURCE
        )
        return {"subjectId": subject_id, "sequence": result.sequence, "warnings": warnings}
    finally:
        ledger.close()


def uninstall(workspace: Path | str) -> dict[str, Any]:
    """Remove Meridian operational state; preserve the evidence record.

    Deletes everything under ``<ws>/.meridian`` except ``ledger/``,
    ``receipts/`` and ``archive/``; deletes the collector signing seed.
    Refuses while ``.meridian/worktrees`` holds agent worktrees — merge or
    remove them first (we never silently discard possibly-unmerged work).
    Never touches the git history or files outside ``.meridian``.
    """
    root = Path(workspace)
    state = root / MERIDIAN_DIR
    if not state.is_dir():
        return {"removed": [], "preserved": [], "wasInstalled": False}
    worktrees = state / "worktrees"
    remaining = [p.name for p in worktrees.iterdir()] if worktrees.is_dir() else []
    if remaining:
        raise CollectorError(
            "FR-M43-14: refusing uninstall: agent worktrees still exist"
            f" under {worktrees} ({sorted(remaining)}) — merge or remove"
            " them first; uninstall never discards possibly-unmerged work"
        )
    removed: list[str] = []
    preserved: list[str] = []
    for child in sorted(state.iterdir()):
        if child.name in PRESERVED_ON_UNINSTALL:
            preserved.append(child.name)
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(child.name)
    return {
        "wasInstalled": True,
        "removed": removed,
        "preserved": preserved,
        "note": (
            "Evidence record preserved under .meridian (ledger, receipts,"
            " archive). Git history and workspace files are untouched."
            " The signing seed was removed."
        ),
    }
