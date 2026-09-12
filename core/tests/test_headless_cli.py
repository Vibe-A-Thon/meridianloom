"""FR-M43-12/13 — the headless collector and verifier.

A customer can operate their own evidence with no extension, no editor and no
running sidecar: export it, verify it, erase a subject from it, and leave
entirely. The last one is why *uninstall* is a command rather than a paragraph
in a document — a tool you can only leave by hand is a tool you cannot really
leave.

Driven as a subprocess throughout, because "usable without the extension" is a
claim about a program somebody runs, not about an importable function.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parents[1]
SEED_HEX = "11" * 32


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(CORE_ROOT)
    # Never inherited: the signing key is passed per-command, so a test cannot
    # pass by accident because the developer happened to export one.
    environment.pop("MERIDIAN_LEDGER_SIGNING_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "meridian_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        cwd=str(cwd) if cwd else None,
        env=environment,
    )


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """A workspace with a real ledger, written the way the sidecar writes it."""
    from meridian_core.ledger import Ledger
    from meridian_core.ledger import keys as ledger_keys

    root = tmp_path / "project"
    (root / ".meridian").mkdir(parents=True)
    ledger = Ledger(
        root / ".meridian" / "ledger",
        ledger_keys.ProvisionedSigningKeyProvider(bytes.fromhex(SEED_HEX)),
    )
    for index in range(1, 4):
        ledger.append(
            {
                "story_id": "HEADLESS-1",
                "phase": "build",
                "loop_id": "L2-task",
                "loop_iteration": 1,
                "actor_id": "developer-agent",
                "actor_version": "1.0.0",
                "actor_kind": "role",
                "policy_version": "policy-v1",
                "action_type": "diff",
                "ts_utc": f"2026-09-01T00:00:{index:06d}Z",
            }
        )
    ledger.close()
    return root


@pytest.fixture()
def key_file(tmp_path) -> Path:
    path = tmp_path / "signing.key"
    path.write_text(SEED_HEX, encoding="utf-8")
    return path


class TestItRefusesToSignWithAKeyNobodyHasSeen:
    def test_export_without_a_key_refuses_and_says_why(self, workspace):
        # The tempting fallback is a throwaway key: the export would succeed
        # and the bundle would verify, against a key that means nothing. That
        # is worse than no bundle, because it looks like evidence.
        result = run_cli("export", "--workspace", str(workspace), "--out", "b.json")
        assert result.returncode == 2
        assert "throwaway" in result.stderr
        assert "MERIDIAN_LEDGER_SIGNING_KEY" in result.stderr

    def test_a_malformed_key_is_refused(self, workspace, tmp_path):
        bad = tmp_path / "bad.key"
        bad.write_text("nowhere near thirty-two bytes", encoding="utf-8")
        result = run_cli(
            "export",
            "--workspace",
            str(workspace),
            "--out",
            str(tmp_path / "b.json"),
            "--signing-key-file",
            str(bad),
        )
        assert result.returncode == 2
        assert "32 raw bytes or 64 hex" in result.stderr


class TestTheRoundTrip:
    def test_export_then_verify(self, workspace, key_file, tmp_path):
        bundle = tmp_path / "bundle.json"
        exported = run_cli(
            "export",
            "--workspace",
            str(workspace),
            "--out",
            str(bundle),
            "--signing-key-file",
            str(key_file),
        )
        assert exported.returncode == 0, exported.stderr
        written = json.loads(bundle.read_text(encoding="utf-8"))
        assert len(written["entries"]) == 3
        # FR-M43-13: the export says what it is, so it stays readable later.
        assert written["schemaVersion"] >= 1
        assert written["redaction"]["defaultProfile"]

        verified = run_cli("verify", str(bundle))
        assert verified.returncode == 0, verified.stdout + verified.stderr

    def test_verify_rejects_a_tampered_bundle(self, workspace, key_file, tmp_path):
        # A verify command that cannot fail is decoration.
        bundle = tmp_path / "bundle.json"
        run_cli(
            "export",
            "--workspace",
            str(workspace),
            "--out",
            str(bundle),
            "--signing-key-file",
            str(key_file),
        )
        document = json.loads(bundle.read_text(encoding="utf-8"))
        document["entries"][0]["storyId"] = "SOMETHING-ELSE"
        bundle.write_text(json.dumps(document), encoding="utf-8")
        assert run_cli("verify", str(bundle)).returncode != 0

    def test_a_missing_ledger_says_where_it_looked(self, tmp_path, key_file):
        empty = tmp_path / "not-a-workspace"
        empty.mkdir()
        result = run_cli(
            "export",
            "--workspace",
            str(empty),
            "--out",
            str(tmp_path / "b.json"),
            "--signing-key-file",
            str(key_file),
        )
        assert result.returncode == 2
        assert ".meridian" in result.stderr


class TestLeaving:
    def test_paths_lists_what_is_there(self, workspace):
        report = json.loads(run_cli("paths", "--workspace", str(workspace)).stdout)
        ledger = next(
            item for item in report["artefacts"] if item["path"].endswith("ledger")
        )
        assert ledger["present"] is True
        assert ledger["bytes"] > 0

    def test_uninstall_deletes_nothing_without_being_told_twice(self, workspace):
        result = run_cli("uninstall", "--workspace", str(workspace))
        assert result.returncode == 0
        assert (workspace / ".meridian" / "ledger").exists()
        # And it points at the export first, because the alternative is a
        # customer discovering afterwards that leaving meant losing.
        assert "export" in result.stderr
        assert "--yes" in result.stderr

    def test_uninstall_with_yes_removes_the_workspace_data(self, workspace):
        result = run_cli("uninstall", "--workspace", str(workspace), "--yes")
        assert result.returncode == 0, result.stderr
        assert not (workspace / ".meridian" / "ledger").exists()
        # The empty container goes too; leaving `.meridian` behind would make
        # "removed" untrue in the only way a user checks it.
        assert not (workspace / ".meridian").exists()

    def test_an_exported_bundle_still_verifies_after_uninstalling(
        self, workspace, key_file, tmp_path
    ):
        """The whole point: what you exported outlives the tool.

        Export, then delete every trace of Meridian from the workspace, then
        verify the bundle. If this failed, "your evidence is yours" would be a
        slogan rather than a property.
        """
        bundle = tmp_path / "bundle.json"
        run_cli(
            "export",
            "--workspace",
            str(workspace),
            "--out",
            str(bundle),
            "--signing-key-file",
            str(key_file),
        )
        run_cli("uninstall", "--workspace", str(workspace), "--yes")
        assert not (workspace / ".meridian").exists()
        verified = run_cli("verify", str(bundle))
        assert verified.returncode == 0, verified.stdout + verified.stderr


class TestErasure:
    def test_erase_shreds_the_subject_and_says_what_that_means(
        self, workspace, key_file
    ):
        result = run_cli(
            "erase",
            "--workspace",
            str(workspace),
            "--subject",
            "subject-a",
            "--reason",
            "request",
            "--signing-key-file",
            str(key_file),
        )
        assert result.returncode == 0, result.stderr
        # Three things a data controller has to be told, none of them obvious.
        assert "unreadable" in result.stderr
        assert "chain still verifies" in result.stderr
        assert "backup" in result.stderr
