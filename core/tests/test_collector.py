"""FR-M43-12…14 (N2 Workstream D task 19): the headless collector — collect,
portable export (with opt-in sink that never cedes the record of
authority), subject erasure, and a truthful uninstall that preserves the
evidence record and never discards possibly-unmerged agent work.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from meridian_core import collector
from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.ledger import privacy as ledger_privacy
from meridian_core.observers import base as observer_base
from meridian_core.observers import manager as observer_manager


class StubObserver:
    """One deterministic observation — a test double for the unit seam;
    the real observer chains have their own suites."""

    vendor = "stub"

    def __init__(self, observation: observer_base.Observation) -> None:
        self._observation = observation

    def observe(self, workspace: Path, now: datetime) -> observer_base.ChainOutcome:
        return observer_base.ChainOutcome(observation=self._observation)

    def health(self) -> dict:
        return {"vendor": self.vendor, "status": "ok", "warnings": []}


def make_observation() -> observer_base.Observation:
    return observer_base.Observation(
        vendor="stub",
        session_id="sess-1",
        confidence="inferred",
        source="test-tier",
        detail="stub observation for collector tests",
        started_at="2026-09-12T10:00:00Z",
        workspace=None,
        agent_id=None,
    )


@pytest.fixture()
def workspace(tmp_path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "src.txt").write_text("user code\n", encoding="utf-8")
    return root


def test_collect_creates_ledger_and_ingests_once(workspace: Path) -> None:
    manager = observer_manager.ObserverManager([StubObserver(make_observation())])

    first = collector.collect(workspace, manager=manager)
    second = collector.collect(workspace, manager=manager)

    assert first["observations"] == 1
    assert first["ingest"]["ingested"] == 1
    # Exactly-once: the second run sees the same event key and replays it.
    assert second["ingest"]["ingested"] == 0
    assert (workspace / ".meridian" / "ledger").is_dir()
    # Signing seed exists, private to the owner (FR-M43-12).
    seed = workspace / ".meridian" / "secrets" / "ledger-signing.seed"
    assert seed.exists()
    assert len(seed.read_text(encoding="ascii").strip()) == 64
    if os.name == "posix":  # NTFS has no POSIX mode bits
        assert stat.S_IMODE(seed.stat().st_mode) & 0o077 == 0


def test_collect_refuses_missing_workspace(tmp_path) -> None:
    with pytest.raises(collector.CollectorError, match="FR-M43-12"):
        collector.collect(tmp_path / "nope")


def _seed_blob_ledger(workspace: Path, subject: str = "alice") -> None:
    ledger = Ledger(workspace / ".meridian" / "ledger", EphemeralSigningKeyProvider())
    ledger.append(
        {
            "story_id": "PRIV-1",
            "phase": "build",
            "loop_id": "L1",
            "loop_iteration": 1,
            "actor_id": "agent",
            "actor_version": "0.0.1",
            "actor_kind": "role",
            "policy_version": "policy-v1",
            "action_type": "diff",
            "input": f"secret of {subject}".encode(),
            "blob_subject": subject,
        }
    )
    ledger.close()


class _SinkHandler(BaseHTTPRequestHandler):
    received: list[bytes] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        length = int(self.headers["Content-Length"])
        type(self).received.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture()
def sink_server():
    _SinkHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _SinkHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/sink"
    server.shutdown()
    thread.join(timeout=5)


def test_export_retains_schema_source_and_redaction_labels(
    workspace: Path, sink_server: str
) -> None:
    _seed_blob_ledger(workspace)
    out = workspace.parent / "export"

    result = collector.export_portable(workspace, out, sink=sink_server)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == bundle["schemaVersion"]
    assert manifest["schemaVersion"] is not None
    # Source identifiers survive; no absolute path leakage (FR-M43-13).
    assert manifest["source"]["kind"] in {"git", "directory"}
    assert "pathDigest" in manifest["source"] or manifest["source"].get("worktreeDigest")
    assert str(workspace) not in (out / "manifest.json").read_text(encoding="utf-8")
    # No consent recorded: the subject is withheld, and the label is named.
    assert manifest["withheldSubjects"] == ["alice"]
    assert result["authorityUnchanged"] is True
    # The sink received a copy...
    assert len(_SinkHandler.received) == 1
    sunk = json.loads(_SinkHandler.received[0])
    assert sunk["manifest"]["recordOfAuthority"] == "local-ledger"
    # ...and the local ledger remains the record of authority.


def test_erase_subject_records_chain_entry(workspace: Path) -> None:
    _seed_blob_ledger(workspace)

    result = collector.erase_subject(workspace, "alice")

    assert result["subjectId"] == "alice"
    ledger = Ledger(workspace / ".meridian" / "ledger", EphemeralSigningKeyProvider())
    try:
        controller = ledger_privacy.PrivacyController(ledger)
        assert any(e.subject_id == "alice" for e in controller.erasures())
    finally:
        ledger.close()


def test_uninstall_preserves_evidence_and_never_touches_source(
    workspace: Path,
) -> None:
    _seed_blob_ledger(workspace)
    state = workspace / ".meridian"
    (state / "receipts").mkdir()
    (state / "policy").mkdir()
    (state / "worktrees").mkdir()
    (state / "secrets").mkdir()

    result = collector.uninstall(workspace)

    assert result["wasInstalled"] is True
    assert set(result["preserved"]) == {"ledger", "receipts"}
    assert "policy" in result["removed"]
    assert "secrets" in result["removed"]  # signing seed must not linger
    assert not (state / "secrets").exists()
    # The user source file and the evidence ledger survive.
    assert (workspace / "src.txt").read_text(encoding="utf-8") == "user code\n"
    assert (state / "ledger").is_dir()


def test_uninstall_refuses_with_existing_worktrees(workspace: Path) -> None:
    worktree = workspace / ".meridian" / "worktrees" / "STORY-1"
    worktree.mkdir(parents=True)
    (worktree / "change.txt").write_text("unmerged agent work\n", encoding="utf-8")

    with pytest.raises(collector.CollectorError, match="FR-M43-14"):
        collector.uninstall(workspace)

    # Nothing was removed, including the worktree.
    assert (worktree / "change.txt").exists()
    assert (workspace / ".meridian" / "worktrees" / "STORY-1").exists()


def test_cli_collect_and_uninstall_round_trip(workspace: Path) -> None:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")

    collect_run = subprocess.run(
        [sys.executable, "-m", "meridian_core", "collect", "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert collect_run.returncode == 0, collect_run.stderr
    assert json.loads(collect_run.stdout)["observations"] >= 0

    uninstall_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian_core",
            "uninstall",
            "--workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert uninstall_run.returncode == 0, uninstall_run.stderr
    assert json.loads(uninstall_run.stdout)["wasInstalled"] is True
