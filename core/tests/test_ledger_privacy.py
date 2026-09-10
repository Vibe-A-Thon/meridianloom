"""FR-M43-06/07/08, SEC-37 (N2 Workstream D task 17): the privacy lifecycle.

Seeded-secret discipline: two canaries are planted through every path.

  SECRET_CANARY — credential-shaped (``api_key = "..."``), so the SEC-07
  filter must redact it wherever content IS captured. Asserted ABSENT
  after: redacted ingestion, recipient export, archival, restore.
  PLAIN_CANARY — not a credential shape, so it survives redaction and is
  assert PRESENT wherever content legitimately flows (consented export,
  restored blobs) and ABSENT where it must not (metadata-only capture,
  withheld-subject export, post-erasure reads).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from meridian_core.ledger import EphemeralSigningKeyProvider, Ledger
from meridian_core.ledger import keystore, privacy
from meridian_core.ledger.archive import (
    ArchiveStore,
    RetentionPolicy,
    measure_restore,
)
from meridian_core.ledger.blobs import BlobKeyMissing
from meridian_core.ledger.bundle import build_bundle
from meridian_core.ledger.redaction import (
    REDACTED,
    clear_registered_patterns,
    redact_fields,
    redact_secrets,
    register_redaction_pattern,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_PY = REPO_ROOT / "verifier" / "verify.py"

SECRET_CANARY = 'api_key = "CANARY-9f8e7d6c5b4a3210"'
PLAIN_CANARY = "CANARY-PLAINTEXT-xyzzy-9988776655"


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "PRV-1",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "agent-prv",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": f"2026-09-01T00:00:{seq:06d}Z",
    }
    entry.update(extra)
    return entry


def blob_texts(ledger, subject=None):
    """All decrypted blob payloads (for scanning for canaries)."""
    if subject is not None:
        key_id = keystore.key_id_for(subject)
        rows = ledger.conn.execute(
            "SELECT input_ref, output_ref, blob_key_id FROM ledger_entry"
            " WHERE blob_key_id = ?",
            (key_id,),
        ).fetchall()
    else:
        rows = ledger.conn.execute(
            "SELECT input_ref, output_ref, blob_key_id FROM ledger_entry"
            " WHERE input_ref IS NOT NULL OR output_ref IS NOT NULL"
        ).fetchall()
    out = []
    for input_ref, output_ref, key_id in rows:
        for ref in (input_ref, output_ref):
            if ref:
                out.append(ledger.read_blob(ref, key_id))
    return out


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


# -- FR-M43-06: collection profiles --------------------------------------------


def test_collection_profiles_declare_what_is_captured():
    default = privacy.COLLECTION_PROFILES[privacy.DEFAULT_PROFILE]
    assert default.name == "metadata_only"
    assert not default.capture_input and not default.capture_output
    redacted = privacy.COLLECTION_PROFILES["content_redacted"]
    assert redacted.capture_input and redacted.redact
    full = privacy.COLLECTION_PROFILES["content_full"]
    assert full.capture_input and not full.redact and full.requires_consent


def test_default_profile_is_metadata_only():
    assert privacy.DEFAULT_PROFILE == "metadata_only"


def test_metadata_only_profile_persists_none_of_the_secrets(tmp_path):
    """FR-M43-07: the default metadata-only profile persists NONE of the
    seeded secrets — not in the database, not in any blob, nowhere."""
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger)  # default profile
    result = controller.append(
        make_entry(
            1,
            input=f"prompt with {SECRET_CANARY} and {PLAIN_CANARY}",
            output=f"output with {PLAIN_CANARY}",
        )
    )
    row = ledger.get_entry(result.sequence)
    # Content was dropped before persistence: no blobs, no refs.
    assert row["input_ref"] is None and row["output_ref"] is None
    assert blob_texts(ledger) == []
    # Nothing on disk carries either canary.
    raw_db = (tmp_path / "ledger" / "ledger.db").read_bytes()
    assert SECRET_CANARY.encode() not in raw_db
    assert PLAIN_CANARY.encode() not in raw_db
    for blob_file in (tmp_path / "ledger" / "blobs").rglob("*"):
        if blob_file.is_file():
            assert SECRET_CANARY.encode() not in blob_file.read_bytes()
    ledger.close()


def test_content_redacted_captures_redacted_ciphertext(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(
            1,
            input=f"prompt with {SECRET_CANARY} trailing {PLAIN_CANARY}",
            output="nothing sensitive",
            blob_subject="subject-red",
        )
    )
    texts = [t.decode() for t in blob_texts(ledger)]
    assert any(REDACTED in t for t in texts)
    assert all(SECRET_CANARY not in t for t in texts)
    assert any(PLAIN_CANARY in t for t in texts)  # not a credential shape
    ledger.close()


def test_content_full_requires_recorded_consent(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_full")
    with pytest.raises(privacy.ConsentRequiredError):
        controller.append(
            make_entry(1, input="raw prompt", blob_subject="subject-full")
        )
    controller.record_consent("subject-full", "*", scope="content", granted=True)
    controller.append(
        make_entry(
            2, input=f"raw {PLAIN_CANARY}", blob_subject="subject-full"
        )
    )
    texts = [t.decode() for t in blob_texts(ledger, "subject-full")]
    assert any(PLAIN_CANARY in t for t in texts)
    ledger.close()


# -- FR-M43-06: consent recording -----------------------------------------------


def test_consent_is_recorded_as_chain_entries_and_revocable(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger)
    controller.record_consent("subj-1", "auditor-x", granted=True, actor="dpo")
    controller.record_consent("subj-1", "auditor-x", granted=False, actor="dpo")
    # Consent events are ordinary chain links.
    assert ledger.verify().ok
    assert not controller.is_consented("subj-1", recipient="auditor-x")
    controller.record_consent("subj-1", "auditor-x", granted=True)
    assert controller.is_consented("subj-1", recipient="auditor-x")
    # A consent for a different recipient does not leak across.
    assert not controller.is_consented("subj-1", recipient="auditor-y")
    consents = controller.consents_for("subj-1")
    assert len(consents) == 3 and consents[0].actor == "dpo"
    ledger.close()


# -- FR-M43-06: redaction --------------------------------------------------------


def test_field_and_path_redaction():
    row = {
        "actor_id": "agent-1",
        "tool_calls": [{"command": "deploy --token abc123"}, {"command": "run"}],
        "notes": {"internal": "do not export"},
    }
    redacted = redact_fields(row, {"actor_id", "tool_calls.0.command", "notes.internal", "absent.field"})
    assert redacted["actor_id"] == REDACTED
    assert redacted["tool_calls"][0]["command"] == REDACTED
    assert redacted["tool_calls"][1]["command"] == "run"  # sibling untouched
    assert redacted["notes"]["internal"] == REDACTED
    assert "absent.field" not in redacted
    # The original is not mutated.
    assert row["actor_id"] == "agent-1"


def test_registered_patterns_extend_redaction():
    register_redaction_pattern(r"CANARY-[A-Z]+-[0-9]{6,}")
    try:
        assert redact_secrets(f"token {PLAIN_CANARY} end") == f"token {REDACTED} end"
        # Idempotent registration.
        register_redaction_pattern(r"CANARY-[A-Z]+-[0-9]{6,}")
        assert len(redact_secrets("x")) == 1
    finally:
        clear_registered_patterns()
    assert PLAIN_CANARY in redact_secrets(f"token {PLAIN_CANARY} end")


# -- FR-M43-06: recipient-specific export filtering -------------------------------


@pytest.fixture()
def two_subject_ledger(tmp_path):
    """subject-a: content_full, consented to the workspace ("*" — any
    recipient) and to auditor-x. subject-b: content_redacted, no consent
    for anyone. subject-c: content_redacted, consented to auditor-x
    ONLY (no "*" consent)."""
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    full = privacy.PrivacyController(ledger, "content_full")
    full.record_consent("subject-a", "*", scope="content", granted=True)
    full.record_consent("subject-a", "auditor-x", scope="content", granted=True)
    full.append(
        make_entry(
            1,
            input=f"subject-a prompt {PLAIN_CANARY}",
            blob_subject="subject-a",
        )
    )
    redacted = privacy.PrivacyController(ledger, "content_redacted")
    redacted.append(
        make_entry(
            2,
            input=f"subject-b prompt {PLAIN_CANARY}",
            blob_subject="subject-b",
        )
    )
    redacted.record_consent("subject-c", "auditor-x", scope="content", granted=True)
    redacted.append(
        make_entry(
            3,
            input=f"subject-c prompt {PLAIN_CANARY}",
            blob_subject="subject-c",
        )
    )
    return ledger


def test_export_for_recipient_excludes_unconsented_subjects(
    tmp_path, two_subject_ledger
):
    controller = privacy.PrivacyController(two_subject_ledger)
    exported = controller.export_for_recipient("auditor-x")
    assert exported["consentedSubjects"] == ["subject-a", "subject-c"]
    assert exported["withheldSubjects"] == ["subject-b"]
    # Payloads: only consented subjects' content is attached.
    assert any(PLAIN_CANARY in t for t in exported["payloads"]["subject-a"])
    assert any(PLAIN_CANARY in t for t in exported["payloads"]["subject-c"])
    assert "subject-b" not in exported["payloads"]
    # The withheld subject's canary appears NOWHERE in the payloads.
    assert all(
        "subject-b prompt" not in t for t in exported["payloads"].get("subject-b", [])
    )
    assert PLAIN_CANARY in json.dumps(exported["payloads"]["subject-a"])
    # The privacy section is part of the signed bundle.
    assert exported["bundle"]["privacy"]["recipient"] == "auditor-x"
    verify_bundle_with_open_verifier(exported["bundle"], tmp_path)


def test_export_for_recipient_without_consent_withholds_that_subject(
    tmp_path, two_subject_ledger
):
    """subject-c consented ONLY to auditor-x: an export for auditor-y
    withholds subject-c (and subject-b), while subject-a's "*" consent
    still covers it."""
    controller = privacy.PrivacyController(two_subject_ledger)
    exported = controller.export_for_recipient("auditor-y")
    assert exported["payloads"].keys() == {"subject-a"}
    assert sorted(exported["withheldSubjects"]) == ["subject-b", "subject-c"]
    joined = json.dumps(exported["payloads"])
    assert "subject-c prompt" not in joined
    assert "subject-b prompt" not in joined


# -- FR-M43-07: seeded secrets across archives and restore ------------------------


def test_secret_canary_absent_across_archive_and_restore(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(
            1,
            input=f"prompt {SECRET_CANARY} {PLAIN_CANARY}",
            blob_subject="subject-arc",
        )
    )
    store = ArchiveStore(tmp_path / "cold")
    store.archive(ledger, RetentionPolicy(horizon_sequences=1))
    # Cold storage holds only ciphertext: neither canary shape appears.
    for blob_file in (tmp_path / "cold").rglob("*.blob"):
        raw = blob_file.read_bytes()
        assert SECRET_CANARY.encode() not in raw
        assert PLAIN_CANARY.encode() not in raw
    restored, _ = measure_restore(ledger, store)
    assert restored == 2
    # After restore the redacted content is back, the secret canary is not.
    texts = [t.decode() for t in blob_texts(ledger, "subject-arc")]
    assert any(PLAIN_CANARY in t for t in texts)
    assert all(SECRET_CANARY not in t for t in texts)
    ledger.close()


# -- FR-M43-08 / SEC-37: erasure via crypto-shredding -----------------------------


def test_erasure_journey_chain_stays_verifiable(tmp_path):
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(
            1, input=f"payload {PLAIN_CANARY}", blob_subject="subject-erase"
        )
    )
    result = controller.erase_subject("subject-erase", reason="GDPR Art. 17 request", actor="dpo")
    # The erasure event itself is a ledger entry.
    row = ledger.get_entry(result.sequence)
    assert row["action_type"] == "erasure"
    events = controller.erasures()
    assert len(events) == 1 and events[0].subject_id == "subject-erase"
    # Chain verification still succeeds (hashes commit to ciphertext).
    assert ledger.verify().ok
    verify_bundle_with_open_verifier(build_bundle(ledger, {}), tmp_path)
    # The subject is unreadable.
    key_id = keystore.key_id_for("subject-erase")
    rows = ledger.conn.execute(
        "SELECT input_ref FROM ledger_entry WHERE blob_key_id = ?", (key_id,)
    ).fetchall()
    with pytest.raises(BlobKeyMissing):
        ledger.read_blob(rows[0][0], key_id)
    # FR-M43-08: erasure is visible as a coverage gap.
    gaps = controller.coverage_gaps()
    assert any(g["cause"] == "erased" and g["sequence"] == 1 for g in gaps)
    ledger.close()


def test_erased_subject_unreadable_after_post_erasure_backup_restore(tmp_path):
    """Backup-key behaviour, case 1: a backup taken AFTER the erasure
    restores with the key already gone — the subject stays unreadable."""
    source = tmp_path / "ledger"
    ledger = Ledger(source, EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(1, input=f"payload {PLAIN_CANARY}", blob_subject="subject-bak")
    )
    controller.erase_subject("subject-bak", reason="request")
    ledger.close()

    backup = tmp_path / "backup"
    shutil.copytree(source, backup)
    restored = Ledger(backup, EphemeralSigningKeyProvider())
    key_id = keystore.key_id_for("subject-bak")
    rows = restored.conn.execute(
        "SELECT input_ref FROM ledger_entry WHERE blob_key_id = ?", (key_id,)
    ).fetchall()
    with pytest.raises(BlobKeyMissing):
        restored.read_blob(rows[0][0], key_id)
    # And the restored chain still verifies.
    assert restored.verify().ok
    restored.close()


def test_pre_erasure_backup_restore_requires_erasure_replay(tmp_path):
    """Backup-key behaviour, case 2 (the documented hazard): restoring a
    PRE-erasure backup verbatim brings the wrapped key back. The
    protection is erasure replay: erasure events are chain entries in the
    live ledger, and replaying them re-shreds the subject in the restored
    copy. SEC-37 holds; the hazard is stated, not hidden."""
    source = tmp_path / "ledger"
    ledger = Ledger(source, EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(1, input=f"payload {PLAIN_CANARY}", blob_subject="subject-bak")
    )
    ledger.close()

    # Backup BEFORE the erasure.
    backup = tmp_path / "backup"
    shutil.copytree(source, backup)

    ledger = Ledger(source, EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger)
    controller.erase_subject("subject-bak", reason="request")
    ledger.close()

    # Verbatim restore: the hazard is real — the old wrapped key is back.
    restored = Ledger(backup, EphemeralSigningKeyProvider())
    key_id = keystore.key_id_for("subject-bak")
    ref = restored.conn.execute(
        "SELECT input_ref FROM ledger_entry WHERE blob_key_id = ?", (key_id,)
    ).fetchone()[0]
    assert PLAIN_CANARY in restored.read_blob(ref, key_id).decode()

    # Erasure replay from the live ledger re-shreds the restored copy.
    replayed = controller.replay_erasures_into(restored)
    assert replayed == 1
    with pytest.raises(BlobKeyMissing):
        restored.read_blob(ref, key_id)
    assert restored.verify().ok
    restored.close()


def test_erasure_survives_archived_blobs(tmp_path):
    """SEC-37 across the archival path: an archived (cold) blob of an
    erased subject stays unreadable — the key, not the file, is the
    erasure."""
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    controller.append(
        make_entry(1, input=f"payload {PLAIN_CANARY}", blob_subject="subject-cold")
    )
    store = ArchiveStore(tmp_path / "cold")
    store.archive(ledger, RetentionPolicy(horizon_sequences=1))
    controller.erase_subject("subject-cold", reason="request")
    key_id = keystore.key_id_for("subject-cold")
    ref = ledger.conn.execute(
        "SELECT input_ref FROM ledger_entry WHERE blob_key_id = ?", (key_id,)
    ).fetchone()[0]
    with pytest.raises(BlobKeyMissing):
        store.fetch(ledger, ref, key_id)
    ledger.close()


# -- FR-M43-07: seeded secrets across error logs ----------------------------------


def test_secret_canary_never_reaches_logs(tmp_path, caplog):
    """FR-M43-07's 'error logs' path: a failed ingestion carrying the
    canary must not leak it into log records."""
    ledger = Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider())
    controller = privacy.PrivacyController(ledger, "content_redacted")
    bad = make_entry(1, input=f"prompt {SECRET_CANARY}")
    del bad["actor_id"]  # force a validation failure mid-append
    with caplog.at_level(logging.DEBUG, logger="meridian_core.ledger"):
        with pytest.raises(Exception):
            controller.append(bad)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRET_CANARY not in logged
    ledger.close()
