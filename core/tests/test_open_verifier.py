"""Open verifier wiring (FR-M36-06, NFR-31, SEC-29; F0 Workstream E task 26).

Real bundles exported from a real ledger are fed to both reference
verifiers: verifier/verify.py (stdlib-only Python, run as a subprocess)
and the Rust meridian-verify binary (verifier/, built with cargo — cargo
IS on PATH in this environment, so the Rust suite genuinely runs; only a
missing cargo produces a skip-and-notice). Tampered bundles must exit 1
from both with actionable stderr.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.ledger.bundle import build_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_PY = REPO_ROOT / "verifier" / "verify.py"
CARGO = shutil.which("cargo")


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "OPEN-1",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-open",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


@pytest.fixture(scope="module")
def bundle_path(tmp_path_factory) -> Path:
    """A real exported bundle on disk, shared by every verifier test."""
    work = tmp_path_factory.mktemp("open-verifier")
    ledger = Ledger(work / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 8):
        ledger.append(make_entry(seq, confidence=0.5, cost_usd=0.01))
    bundle = build_bundle(ledger, {})
    ledger.close()
    path = work / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def tampered_copy(bundle_path: Path, tmp_path: Path, name: str, mutate) -> Path:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    mutate(bundle)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


TAMPERS = {
    "payload": lambda b: b["entries"][2]["hashPayload"].update(phase="evil"),
    "proof": lambda b: b["proofs"]["inclusion"][0]["path"].__setitem__(0, "00" * 32),
    "tree-head": lambda b: b["treeHead"].update(rootHash="ab" * 32),
    "signature": lambda b: b["signature"].update(signature="ff" * 64),
    "compliance": lambda b: b.pop("compliance"),
}


def run_verify_py(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_PY), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


class TestPythonVerifier:
    def test_valid_bundle_exits_zero(self, bundle_path):
        result = run_verify_py(bundle_path)
        assert result.returncode == 0, result.stderr
        assert "OK: bundle verifies" in result.stdout

    def test_valid_bundle_from_stdin_exits_zero(self, bundle_path):
        result = subprocess.run(
            [sys.executable, str(VERIFY_PY), "-"],
            input=bundle_path.read_bytes(),
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")

    @pytest.mark.parametrize("tamper", sorted(TAMPERS))
    def test_tampered_bundle_exits_one(self, bundle_path, tmp_path, tamper):
        path = tampered_copy(bundle_path, tmp_path, tamper, TAMPERS[tamper])
        result = run_verify_py(path)
        assert result.returncode == 1
        assert "FAIL:" in result.stderr

    def test_garbage_input_is_an_error_not_a_crash(self, tmp_path):
        path = tmp_path / "garbage.json"
        path.write_text("{ not json", encoding="utf-8")
        result = run_verify_py(path)
        assert result.returncode == 2
        assert "not valid JSON" in result.stderr

    def test_missing_file_is_an_error_not_a_crash(self, tmp_path):
        result = run_verify_py(tmp_path / "absent.json")
        assert result.returncode == 2
        assert "cannot read bundle" in result.stderr


@pytest.fixture(scope="module")
def rust_binary() -> Path | None:
    """Build meridian-verify once for the module. cargo is on PATH in this
    environment (rustc 1.97.1) so this genuinely runs; a machine without
    cargo skips with a notice rather than failing."""
    if CARGO is None:
        pytest.skip("cargo not on PATH; skipping the Rust verifier suite")
        return None
    build = subprocess.run(
        [CARGO, "build"],
        cwd=REPO_ROOT / "verifier",
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    suffix = ".exe" if os.name == "nt" else ""
    return REPO_ROOT / "verifier" / "target" / "debug" / f"meridian-verify{suffix}"


class TestRustVerifier:
    def test_cargo_test_passes(self):
        """The Rust verifier's own suite must be green where cargo exists."""
        if CARGO is None:
            pytest.skip("cargo not on PATH; skipping the Rust verifier suite")
        result = subprocess.run(
            [CARGO, "test"],
            cwd=REPO_ROOT / "verifier",
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert "test result: ok" in result.stdout

    def test_binary_matches_python_verifier_on_valid_bundle(
        self, bundle_path, rust_binary
    ):
        result = subprocess.run(
            [str(rust_binary), str(bundle_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert "OK: bundle verifies" in result.stdout

    @pytest.mark.parametrize("tamper", sorted(TAMPERS))
    def test_binary_rejects_tampering(self, bundle_path, tmp_path, rust_binary, tamper):
        path = tampered_copy(bundle_path, tmp_path, tamper, TAMPERS[tamper])
        result = subprocess.run(
            [str(rust_binary), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert result.returncode == 1
        assert "FAIL:" in result.stderr

    def test_binary_reads_stdin(self, bundle_path, rust_binary):
        result = subprocess.run(
            [str(rust_binary), "-"],
            input=bundle_path.read_bytes(),
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
