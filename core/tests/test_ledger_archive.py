"""FR-M43-04 / FR-M43-05 / NFR-38 (N2 Workstream D task 16): multi-year
retention with compaction and an archival path, proven end to end:
archive -> restore -> re-verification, with published measurements.

FR-M43-05's numbers (storage growth per 10,000 entries; restore time for
a three-year archive) are measured here and printed; NFR-38's budget is
asserted against archive.RESTORE_BUDGET_S.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.ledger import archive as arch
from meridian_core.ledger import merkle
from meridian_core.ledger.bundle import build_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_PY = REPO_ROOT / "verifier" / "verify.py"

THREE_YEARS_DAYS = 3 * 365


def make_entry(seq: int, subject: str = "story:ARC-1", **extra) -> dict:
    entry = {
        "story_id": "ARC-1",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-arc",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    if "input" in extra or "output" in extra:
        entry["blob_subject"] = subject
    return entry


@pytest.fixture()
def ledger_with_blobs(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    contents: dict[int, tuple[str, str]] = {}
    for seq in range(1, 9):
        text_in = f"prompt {seq}: archive me"
        text_out = f"result {seq}"
        ledger.append(
            make_entry(seq, input=text_in, output=text_out)
        )
        contents[seq] = (text_in, text_out)
    ledger.emit_tree_head_now()
    yield ledger, contents
    ledger.close()


def verify_bundle_with_open_verifier(bundle: dict, tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VERIFY_PY), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


# -- retention cutoff (FR-M43-04) ----------------------------------------------


def test_retention_cutoff_by_sequence(ledger_with_blobs):
    ledger, _ = ledger_with_blobs
    policy = arch.RetentionPolicy(horizon_sequences=5)
    assert arch.retention_cutoff(policy, ledger) == 5


def test_retention_cutoff_by_days_is_multi_year_shape(ledger_with_blobs):
    ledger, _ = ledger_with_blobs
    policy = arch.RetentionPolicy(horizon_days=THREE_YEARS_DAYS)
    # All test entries are 2026-09-01; "now" far in the future archives
    # the whole chain — the multi-year horizon.
    now = datetime(2029, 10, 1, tzinfo=timezone.utc)
    assert arch.retention_cutoff(policy, ledger, now=now) == 8
    # A horizon that keeps everything recent cuts nothing.
    recent = datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert arch.retention_cutoff(policy, ledger, now=recent) == 0


def test_retention_policy_requires_a_horizon():
    with pytest.raises(ValueError):
        arch.RetentionPolicy()


# -- archival (FR-M43-04) -------------------------------------------------------


def test_archive_moves_blobs_below_cutoff_to_cold_storage(tmp_path, ledger_with_blobs):
    ledger, _ = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    policy = arch.RetentionPolicy(horizon_sequences=4)
    manifest = store.archive(ledger, policy)
    assert manifest.cutoff_sequence == 4
    archived_refs = {f.ref for f in manifest.files}
    assert len(archived_refs) == 8  # 4 entries x (input + output)
    # Hot store no longer has the archived refs; entries above the cutoff
    # (5..8 -> 8 blobs) stay hot; cold store has exactly the 8 archived.
    hot_root = Path(ledger.dir) / "blobs"
    assert len(list(hot_root.rglob("*.blob"))) == 8
    assert len(list((tmp_path / "cold").rglob("*.blob"))) == 8
    # The digests stay committed in the chain rows.
    row = ledger.get_entry(1)
    assert row["input_digest"] and row["output_digest"]
    assert ledger.verify().ok


def test_archival_is_idempotent(tmp_path, ledger_with_blobs):
    ledger, _ = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    policy = arch.RetentionPolicy(horizon_sequences=8)
    first = store.archive(ledger, policy)
    assert len(first.files) == 16
    second = store.archive(ledger, policy)
    assert second.files == ()


# -- verification through archive and restore (FR-M43-05) -----------------------


def test_archived_entry_still_verifies_against_tree_head_and_inclusion(
    tmp_path, ledger_with_blobs
):
    """FR-M43-05: archive -> the signed bundle still verifies, the entry
    hash still recomputes, the inclusion proof still anchors the entry —
    because the chain commits to digests in rows, which never move."""
    ledger, _ = ledger_with_blobs
    bundle = build_bundle(ledger, {})
    store = arch.ArchiveStore(tmp_path / "cold")
    store.archive(ledger, arch.RetentionPolicy(horizon_sequences=8))
    # Everything below holds with the hot blob store EMPTY.
    verify_bundle_with_open_verifier(bundle, tmp_path)
    entry = bundle["entries"][4]
    from meridian_core.ledger.canonical import entry_hash as recompute

    assert recompute(
        bytes.fromhex(entry["previousHash"]), entry["hashPayload"]
    ) == bytes.fromhex(entry["entryHash"])
    proof = next(p for p in bundle["proofs"]["inclusion"] if p["sequence"] == 5)
    assert merkle.verify_inclusion(
        proof["leafIndex"],
        bytes.fromhex(entry["entryHash"]),
        bundle["proofs"]["treeSize"],
        [bytes.fromhex(node) for node in proof["path"]],
        bytes.fromhex(bundle["proofs"]["rootHash"]),
    )


def test_restore_roundtrip_content_matches_and_chain_verifies(
    tmp_path, ledger_with_blobs
):
    ledger, contents = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    store.archive(ledger, arch.RetentionPolicy(horizon_sequences=8))
    restored, elapsed = arch.measure_restore(ledger, store)
    assert restored == 16
    assert elapsed < arch.RESTORE_BUDGET_S
    for seq, (text_in, text_out) in contents.items():
        row = ledger.get_entry(seq)
        assert ledger.read_blob(row["input_ref"], row["blob_key_id"]).decode() == text_in
        assert ledger.read_blob(row["output_ref"], row["blob_key_id"]).decode() == text_out


def test_fetch_restores_single_blob_on_demand(tmp_path, ledger_with_blobs):
    ledger, contents = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    store.archive(ledger, arch.RetentionPolicy(horizon_sequences=8))
    row = ledger.get_entry(3)
    data = store.fetch(ledger, row["input_ref"], row["blob_key_id"])
    assert data.decode() == contents[3][0]
    # The on-demand restore also put the ciphertext back in the hot store.
    assert (Path(ledger.dir) / "blobs" / row["input_ref"]).is_file()


def test_restore_detects_tampered_cold_blob(tmp_path, ledger_with_blobs):
    ledger, _ = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    store.archive(ledger, arch.RetentionPolicy(horizon_sequences=8))
    cold_file = next((tmp_path / "cold").rglob("*.blob"))
    cold_file.write_bytes(b"tampered" * 32)
    with pytest.raises(arch.ArchiveError):
        store.restore(ledger)


def test_restore_checks_digests_against_ledger_rows(tmp_path, ledger_with_blobs):
    """The manifest alone could be rewritten with the blobs; the ledger
    rows (committed into the chain) cannot. Restore cross-checks both."""
    ledger, _ = ledger_with_blobs
    store = arch.ArchiveStore(tmp_path / "cold")
    store.archive(ledger, arch.RetentionPolicy(horizon_sequences=8))
    cold_file = next((tmp_path / "cold").rglob("*.blob"))
    import hashlib

    fake = b"forged content"
    cold_file.write_bytes(fake)
    # Keep the manifest consistent with the forgery...
    manifest_path = next((tmp_path / "cold").glob("*/manifest.json"))
    data = json.loads(manifest_path.read_bytes())
    for f in data["files"]:
        if f["ref"] == cold_file.relative_to(manifest_path.parent / "blobs").as_posix():
            f["digest"] = hashlib.sha256(fake).hexdigest()
    manifest_path.write_bytes(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    )
    # ...and the ledger-row digest check still catches it.
    with pytest.raises(arch.ArchiveError):
        store.restore(ledger)


# -- FR-M43-05 / NFR-38: published measurements ---------------------------------


@pytest.mark.perf
def test_storage_growth_per_10k_entries_and_three_year_restore(tmp_path):
    """FR-M43-05: publish storage growth per 10,000 entries. NFR-38: a
    three-year archive restores and re-verifies within the documented
    budget. Every 10th entry carries input+output blobs (the realistic
    metadata-heavy mix); the measured figure includes the database."""
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    started = time.perf_counter()
    batch = []
    for seq in range(1, 10_001):
        entry = make_entry(seq)
        # A three-year-old corpus: timestamps predate the horizon.
        entry["ts_utc"] = f"2023-08-01T00:00:{seq % 60:06d}Z"
        if seq % 10 == 0:
            entry["input"] = f"prompt {seq}: " + "x" * 100
            entry["output"] = f"result {seq}: " + "y" * 60
            entry["blob_subject"] = "story:ARC-BULK"
        batch.append(entry)
        if len(batch) == 1000:
            ledger.append_many(batch)
            batch = []
    if batch:
        ledger.append_many(batch)
    build_s = time.perf_counter() - started
    ledger.emit_tree_head_now()

    db_bytes = (Path(ledger.dir) / "ledger.db").stat().st_size
    blob_bytes = sum(
        f.stat().st_size for f in (Path(ledger.dir) / "blobs").rglob("*.blob")
    )
    total_mb = (db_bytes + blob_bytes) / 1_000_000
    print(
        f"\nFR-M43-05 storage growth per 10,000 entries: {total_mb:.2f} MB "
        f"(db {db_bytes / 1_000_000:.2f} MB + blobs {blob_bytes / 1_000_000:.2f} MB; "
        f"build {build_s:.1f}s)"
    )

    # The three-year archival path over the whole corpus.
    bundle = build_bundle(ledger, {})
    store = arch.ArchiveStore(tmp_path / "cold")
    manifest = store.archive(ledger, arch.RetentionPolicy(horizon_days=THREE_YEARS_DAYS))
    assert len(manifest.files) == 2_000
    hot_after = sum(
        f.stat().st_size for f in (Path(ledger.dir) / "blobs").rglob("*.blob")
    )
    assert hot_after == 0
    # Archival never weakens the record: the signed bundle still verifies.
    verify_bundle_with_open_verifier(bundle, tmp_path)

    restored, elapsed = arch.measure_restore(ledger, store)
    assert restored == 2_000
    assert elapsed < arch.RESTORE_BUDGET_S, (
        f"NFR-38 restore budget exceeded: {elapsed:.2f}s > {arch.RESTORE_BUDGET_S}s"
    )
    row = ledger.get_entry(10_000)
    assert ledger.read_blob(row["input_ref"], row["blob_key_id"]).startswith(b"prompt 10000")
    print(
        f"NFR-38 three-year archive restore + chain re-verification: "
        f"{restored} blobs in {elapsed:.2f}s (budget {arch.RESTORE_BUDGET_S:.0f}s)"
    )
    ledger.close()
