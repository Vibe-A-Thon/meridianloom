"""FR-M43-02 / FR-M43-03 (N2 Workstream D task 14): three separate verdicts.

The package-side logic (ledger/witness.py), the open Python verifier
(verifier/verify.py --witness) and the Rust verifier (verifier/,
--witness) must all agree:

  - a changed entry fails ONLY valid_signature;
  - an un-enrolled signer fails ONLY trusted_signer;
  - rollback/truncation and wholesale replacement (a re-signed fork)
    fail ONLY evidence_coverage — a witness mismatch is
    valid_signature: True + evidence_coverage: False, never a
    signature failure;
  - with no witness, coverage fails with the stated FR-M43-03
    limitation, and the classic-mode interface says so on stderr.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from meridian_core.ledger import (
    EphemeralSigningKeyProvider,
    Ledger,
    ProvisionedSigningKeyProvider,
)
from meridian_core.ledger import receipts as rc
from meridian_core.ledger import witness
from meridian_core.ledger.bundle import build_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_PY = REPO_ROOT / "verifier" / "verify.py"
CARGO = shutil.which("cargo")
SEED = bytes(range(32))


def make_entry(seq: int, story: str = "VDCT-1", **extra) -> dict:
    entry = {
        "story_id": story,
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-vdct",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


def wire_head(ledger) -> dict:
    row = ledger.latest_tree_head()
    return {
        "seq": row["seq"],
        "rootHash": row["root_hash"].hex(),
        "signedAt": row["signed_at"],
        "signature": row["signature"].hex(),
    }


@pytest.fixture()
def witnessed(tmp_path):
    """A ledger, a witness key, and a receipt countersigned at the tip."""
    ledger = Ledger(tmp_path / "ledger", ProvisionedSigningKeyProvider(SEED))
    for seq in range(1, 9):
        ledger.append(make_entry(seq))
    ledger.emit_tree_head_now()
    witness_key = Ed25519PrivateKey.generate()
    receipt = rc.make_receipt(
        wire_head(ledger), ledger.signing_public_key, "customer-witness-1", witness_key
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    keys_path = tmp_path / "trusted-keys.txt"
    keys_path.write_text(
        base64.b64encode(ledger.signing_public_key).decode() + "\n", encoding="utf-8"
    )
    wkeys_path = tmp_path / "trusted-witness-keys.txt"
    wkeys_path.write_text(
        base64.b64encode(witness_key.public_key().public_bytes_raw()).decode() + "\n",
        encoding="utf-8",
    )
    return {
        "ledger": ledger,
        "bundle": build_bundle(ledger, {}),
        "receipt": receipt,
        "receipt_path": receipt_path,
        "keys_path": keys_path,
        "wkeys_path": wkeys_path,
        "witness_key": witness_key,
    }


def run_verify_py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_PY), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


# -- package-side verdicts ----------------------------------------------------


def test_all_three_verdicts_pass(witnessed):
    v = witness.verify_bundle_verdicts(
        witnessed["bundle"],
        receipts=[witnessed["receipt"]],
        trusted_keys={witnessed["ledger"].signing_public_key},
        trusted_witness_keys={witnessed["witness_key"].public_key().public_bytes_raw()},
    )
    assert v.valid_signature and v.trusted_signer and v.evidence_coverage


def test_changed_entry_fails_only_valid_signature(witnessed):
    bundle = json.loads(json.dumps(witnessed["bundle"]))
    bundle["entries"][3]["hashPayload"]["phase"] = "evil"
    v = witness.verify_bundle_verdicts(
        bundle,
        receipts=[witnessed["receipt"]],
        trusted_keys={witnessed["ledger"].signing_public_key},
    )
    assert not v.valid_signature
    assert v.trusted_signer is True
    assert any("entry 4: entryHash" in p for p in v.problems)


def test_untrusted_signer_fails_only_trusted_signer(witnessed):
    v = witness.verify_bundle_verdicts(
        witnessed["bundle"],
        receipts=[witnessed["receipt"]],
        trusted_keys={b"\x00" * 32},
    )
    assert v.valid_signature
    assert v.trusted_signer is False
    assert v.evidence_coverage


def test_no_trusted_set_means_no_opinion(witnessed):
    v = witness.verify_bundle_verdicts(witnessed["bundle"], receipts=[witnessed["receipt"]])
    assert v.trusted_signer is None
    assert v.valid_signature and v.evidence_coverage


def test_truncated_export_is_rollback_not_signature_failure(witnessed):
    """A bundle exported over 1..4 while the witness recorded the root at
    sequence 8: signatures are fine, coverage fails."""
    partial = build_bundle(witnessed["ledger"], {"toSequence": 4})
    v = witness.verify_bundle_verdicts(
        partial,
        receipts=[witnessed["receipt"]],
        trusted_keys={witnessed["ledger"].signing_public_key},
    )
    assert v.valid_signature, v.problems
    assert not v.evidence_coverage
    assert "rollback/truncation" in v.detail


def test_wholesale_replacement_is_valid_sig_true_coverage_false(tmp_path):
    """The FR-M43-02 headline: an administrator rebuilds the ledger from
    the SAME enrolled signing key (same seed). Every signature verifies;
    only the witness catches the fork."""
    fork = Ledger(tmp_path / "fork", ProvisionedSigningKeyProvider(SEED))
    for seq in range(1, 9):
        fork.append(make_entry(seq, story="VDCT-FORK"))
    fork.emit_tree_head_now()
    fork_bundle = build_bundle(fork, {})
    fork.close()

    witness_key = Ed25519PrivateKey.generate()
    original = Ledger(tmp_path / "orig", ProvisionedSigningKeyProvider(SEED))
    for seq in range(1, 9):
        original.append(make_entry(seq, story="VDCT-1"))
    original.emit_tree_head_now()
    receipt = rc.make_receipt(
        wire_head(original), original.signing_public_key, "customer-witness-1", witness_key
    )
    original.close()

    v = witness.verify_bundle_verdicts(
        fork_bundle,
        receipts=[receipt],
        trusted_keys={ProvisionedSigningKeyProvider(SEED).private_key().public_key().public_bytes_raw()},
    )
    assert v.valid_signature, v.problems  # NOT a signature failure
    assert v.trusted_signer is True        # the key is legitimately enrolled
    assert not v.evidence_coverage
    assert "wholesale replacement or fork" in v.detail


def test_no_receipts_states_fr_m43_03_limitation(witnessed):
    v = witness.verify_bundle_verdicts(witnessed["bundle"])
    assert v.valid_signature
    assert not v.evidence_coverage
    assert v.detail == witness.UNWITNESSED_LIMITATION
    assert "wholesale ledger replacement" in v.detail


def test_unsigned_reception_receipt_counts_for_coverage(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 5):
        ledger.append(make_entry(seq))
    ledger.emit_tree_head_now()
    receipt = rc.make_receipt(wire_head(ledger), ledger.signing_public_key, "local-file-store")
    bundle = build_bundle(ledger, {})
    ledger.close()
    v = witness.verify_bundle_verdicts(bundle, receipts=[receipt])
    assert v.evidence_coverage
    assert "reception receipt" in v.detail


def test_unpinned_witness_key_does_not_count(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 5):
        ledger.append(make_entry(seq))
    ledger.emit_tree_head_now()
    witness_key = Ed25519PrivateKey.generate()
    receipt = rc.make_receipt(
        wire_head(ledger), ledger.signing_public_key, "self-asserted", witness_key
    )
    bundle = build_bundle(ledger, {})
    ledger.close()
    v = witness.verify_bundle_verdicts(
        bundle, receipts=[receipt], trusted_witness_keys={b"\x01" * 32}
    )
    assert v.valid_signature
    assert not v.evidence_coverage
    assert "no usable witness receipts" in v.detail


def test_receipt_with_forged_ledger_head_is_ignored(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    for seq in range(1, 5):
        ledger.append(make_entry(seq))
    ledger.emit_tree_head_now()
    witness_key = Ed25519PrivateKey.generate()
    receipt = rc.make_receipt(
        wire_head(ledger), ledger.signing_public_key, "w", witness_key
    )
    # An attacker swaps in a root the ledger signer never signed.
    receipt["treeHead"]["rootHash"] = "ab" * 32
    receipt["witnessSignature"] = witness_key.sign(rc._receipt_body(receipt)).hex()
    bundle = build_bundle(ledger, {})
    ledger.close()
    v = witness.verify_bundle_verdicts(bundle, receipts=[receipt])
    assert not v.evidence_coverage
    assert "no usable witness receipts" in v.detail


# -- open Python verifier CLI --------------------------------------------------


def test_verify_py_witness_mode_all_pass_from_stdin(witnessed):
    result = subprocess.run(
        [
            sys.executable, str(VERIFY_PY), "-",
            "--witness", str(witnessed["receipt_path"]),
            "--trusted-keys", str(witnessed["keys_path"]),
            "--trusted-witness-keys", str(witnessed["wkeys_path"]),
        ],
        input=json.dumps(witnessed["bundle"]).encode(),
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_verify_py_witness_mode_all_pass_from_file(tmp_path, witnessed):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(witnessed["bundle"]), encoding="utf-8")
    result = run_verify_py(
        str(bundle_path),
        "--witness", str(witnessed["receipt_path"]),
        "--trusted-keys", str(witnessed["keys_path"]),
        "--trusted-witness-keys", str(witnessed["wkeys_path"]),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "VERDICT valid_signature: pass" in result.stdout
    assert "VERDICT trusted_signer: pass" in result.stdout
    assert "VERDICT evidence_coverage: pass" in result.stdout


def test_verify_py_fork_reports_coverage_failure_not_signature_failure(
    tmp_path, witnessed
):
    """End-to-end FR-M43-02 shape through the CLI: the fork's bundle is
    honestly signed, so valid_signature passes and evidence_coverage
    fails — the witness mismatch is NOT a signature failure."""
    fork = Ledger(tmp_path / "fork", ProvisionedSigningKeyProvider(SEED))
    for seq in range(1, 9):
        fork.append(make_entry(seq, story="VDCT-FORK"))
    fork_bundle = build_bundle(fork, {})
    fork.close()
    bundle_path = tmp_path / "fork-bundle.json"
    bundle_path.write_text(json.dumps(fork_bundle), encoding="utf-8")
    result = run_verify_py(
        str(bundle_path),
        "--witness", str(witnessed["receipt_path"]),
        "--trusted-keys", str(witnessed["keys_path"]),
    )
    assert result.returncode == 1
    assert "VERDICT valid_signature: pass" in result.stdout
    assert "VERDICT trusted_signer: pass" in result.stdout
    assert "VERDICT evidence_coverage: FAIL" in result.stdout
    assert "wholesale replacement or fork" in result.stdout
    assert "signature problem" not in result.stdout


def test_verify_py_truncation_via_witness(tmp_path, witnessed):
    partial = build_bundle(witnessed["ledger"], {"toSequence": 4})
    bundle_path = tmp_path / "partial.json"
    bundle_path.write_text(json.dumps(partial), encoding="utf-8")
    result = run_verify_py(
        str(bundle_path),
        "--witness", str(witnessed["receipt_path"]),
        "--trusted-keys", str(witnessed["keys_path"]),
    )
    assert result.returncode == 1
    assert "VERDICT valid_signature: pass" in result.stdout
    assert "VERDICT evidence_coverage: FAIL" in result.stdout
    assert "rollback/truncation" in result.stdout


def test_verify_py_changed_entry_fails_signature_verdict(tmp_path, witnessed):
    bundle = json.loads(json.dumps(witnessed["bundle"]))
    bundle["entries"][2]["hashPayload"]["action_type"] = "evil"
    bundle_path = tmp_path / "tampered.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    result = run_verify_py(
        str(bundle_path),
        "--witness", str(witnessed["receipt_path"]),
        "--trusted-keys", str(witnessed["keys_path"]),
    )
    assert result.returncode == 1
    assert "VERDICT valid_signature: FAIL" in result.stdout
    assert "signature problem: entry 3: entryHash" in result.stdout


def test_verify_py_classic_mode_states_unwitnessed_limitation(tmp_path, witnessed):
    """FR-M43-03: the classic interface says the limitation out loud."""
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(witnessed["bundle"]), encoding="utf-8")
    result = run_verify_py(str(bundle_path))
    assert result.returncode == 0, result.stderr
    assert "OK: bundle verifies" in result.stdout
    assert "wholesale ledger replacement" in result.stderr
    assert "NOTE:" in result.stderr


def test_verify_py_bad_trusted_keys_file_is_usage_error(tmp_path, witnessed):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(witnessed["bundle"]), encoding="utf-8")
    bad_keys = tmp_path / "bad-keys.txt"
    bad_keys.write_text("not base64 !!!\n", encoding="utf-8")
    result = run_verify_py(str(bundle_path), "--trusted-keys", str(bad_keys))
    assert result.returncode == 2


# -- Rust verifier CLI ---------------------------------------------------------


@pytest.fixture(scope="module")
def rust_binary() -> Path | None:
    if CARGO is None:
        pytest.skip("cargo not on PATH; skipping the Rust verifier suite")
    build = subprocess.run(
        [CARGO, "build"], cwd=REPO_ROOT / "verifier",
        capture_output=True, text=True, timeout=600,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    suffix = ".exe" if os.name == "nt" else ""
    return REPO_ROOT / "verifier" / "target" / "debug" / f"meridian-verify{suffix}"


def test_rust_verdict_mode_matches_python(witnessed, rust_binary, tmp_path):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(witnessed["bundle"]), encoding="utf-8")
    ok = subprocess.run(
        [
            str(rust_binary), str(bundle_path),
            "--witness", str(witnessed["receipt_path"]),
            "--trusted-keys", str(witnessed["keys_path"]),
            "--trusted-witness-keys", str(witnessed["wkeys_path"]),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert ok.returncode == 0, ok.stderr + ok.stdout
    assert "VERDICT valid_signature: pass" in ok.stdout

    fork = Ledger(tmp_path / "fork", ProvisionedSigningKeyProvider(SEED))
    for seq in range(1, 9):
        fork.append(make_entry(seq, story="VDCT-FORK"))
    fork_bundle = build_bundle(fork, {})
    fork.close()
    fork_path = tmp_path / "fork.json"
    fork_path.write_text(json.dumps(fork_bundle), encoding="utf-8")
    bad = subprocess.run(
        [
            str(rust_binary), str(fork_path),
            "--witness", str(witnessed["receipt_path"]),
            "--trusted-keys", str(witnessed["keys_path"]),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert bad.returncode == 1
    assert "VERDICT valid_signature: pass" in bad.stdout
    assert "VERDICT evidence_coverage: FAIL" in bad.stdout
    assert "wholesale replacement or fork" in bad.stdout


def test_rust_classic_mode_states_unwitnessed_limitation(witnessed, rust_binary, tmp_path):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(witnessed["bundle"]), encoding="utf-8")
    result = subprocess.run(
        [str(rust_binary), str(bundle_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "wholesale ledger replacement" in result.stderr
