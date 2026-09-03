"""Tests for the encrypted content-addressed blob store (FR-M10-07).

Proves: content addressing by ciphertext hash, AES-GCM round-trip,
tamper and wrong-key detection, SEC-07 redaction before persistence,
per-subject key persistence across reopen, and crypto-shredding
(FR-M10-14 groundwork): destroying a subject key makes its blobs
unreadable while the row and chain stay intact.
"""

from __future__ import annotations

import hashlib

import pytest

from meridian_core.ledger import (
    BlobKeyMissing,
    BlobNotFound,
    BlobStore,
    BlobTampered,
    EphemeralBlobKeyStore,
    EphemeralSigningKeyProvider,
    Ledger,
    WrappedBlobKeyStore,
    key_id_for,
    redact_secrets,
)


@pytest.fixture()
def keys():
    return EphemeralBlobKeyStore()


@pytest.fixture()
def store(tmp_path, keys):
    return BlobStore(tmp_path / "blobs", keys)


def make_entry(seq: int, **extra) -> dict:
    entry = {
        "story_id": "EDB-12345",
        "phase": "build",
        "loop_id": "L2-task",
        "loop_iteration": 1,
        "actor_id": "developer-agent",
        "actor_version": "0.0.1",
        "actor_kind": "role",
        "policy_version": "policy-v1",
        "action_type": "diff",
        "ts_utc": "2026-09-01T00:00:00.000001Z",
    }
    entry.update(extra)
    return entry


class TestBlobStore:
    def test_round_trip(self, store, keys):
        key_id = keys.key_for("subject-a")
        digest, ref = store.put(b"hello provenance", key_id)
        assert store.get(ref, key_id) == b"hello provenance"

    def test_address_is_ciphertext_hash(self, store, keys):
        key_id = keys.key_for("subject-a")
        digest, ref = store.put(b"payload", key_id)
        blob = (store._root / ref).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest
        assert ref.endswith(".blob")

    def test_same_subject_key_idempotent(self, keys):
        assert keys.key_for("subject-a") == keys.key_for("subject-a")
        assert keys.key_for("subject-a") != keys.key_for("subject-b")

    def test_ciphertext_not_plaintext_on_disk(self, store, keys, tmp_path):
        key_id = keys.key_for("subject-a")
        _digest, ref = store.put(b"the actual prompt text", key_id)
        blob = (store._root / ref).read_bytes()
        assert b"the actual prompt text" not in blob

    def test_random_nonce_means_no_dedup(self, store, keys):
        key_id = keys.key_for("subject-a")
        d1, _ = store.put(b"same", key_id)
        d2, _ = store.put(b"same", key_id)
        assert d1 != d2

    def test_tampered_ciphertext_detected(self, store, keys):
        key_id = keys.key_for("subject-a")
        _digest, ref = store.put(b"integrity", key_id)
        path = store._root / ref
        blob = bytearray(path.read_bytes())
        blob[-1] ^= 0x01
        path.write_bytes(bytes(blob))
        with pytest.raises(BlobTampered):
            store.get(ref, key_id)

    def test_wrong_key_detected(self, store, keys):
        key_a = keys.key_for("subject-a")
        _digest, ref = store.put(b"confidential to a", key_a)
        key_b = keys.key_for("subject-b")
        with pytest.raises(BlobTampered):
            store.get(ref, key_b)

    def test_missing_key_is_a_shred_not_a_crash(self, store):
        with pytest.raises(BlobKeyMissing):
            store.put(b"x", "bk:never-created")

    def test_missing_file_raises(self, store, keys):
        key_id = keys.key_for("subject-a")
        with pytest.raises(BlobNotFound):
            store.get("00/nope.blob", key_id)


class TestRedaction:
    def test_aws_key_redacted(self):
        text = "credentials AKIAIOSFODNN7EXAMPLE for staging"
        assert "AKIAIOSFODNN7EXAMPLE" not in redact_secrets(text)
        assert "[REDACTED]" in redact_secrets(text)

    def test_github_token_redacted(self):
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0"
        assert token not in redact_secrets(f"push with {token} now")

    def test_pem_private_key_redacted(self):
        pem = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
            "-----END PRIVATE KEY-----"
        )
        redacted = redact_secrets(f"here: {pem}")
        assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in redacted
        assert "[REDACTED-PRIVATE-KEY]" in redacted

    def test_generic_assignment_redacted(self):
        assert redact_secrets('api_key = "supersecretvalue123"') == (
            'api_key = "[REDACTED]"'
        )
        assert redact_secrets("password: hunter2hunter2") == "password: [REDACTED]"

    def test_innocent_text_untouched(self):
        text = "def add(a, b):\n    return a + b  # simple"
        assert redact_secrets(text) == text


class TestLedgerBlobIntegration:
    def test_append_stores_input_output_as_blobs(self, tmp_path):
        with Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()) as led:
            result = led.append(
                make_entry(
                    1,
                    input="write the handler",
                    output="done: diff applied",
                    blob_subject="story:EDB-12345",
                )
            )
            row = led.conn.execute(
                "SELECT input_digest, input_ref, output_digest, output_ref,"
                " blob_key_id FROM ledger_entry WHERE seq = 1"
            ).fetchone()
            input_digest, input_ref, _od, output_ref, key_id = row
            assert key_id == key_id_for("story:EDB-12345")
            assert input_ref is not None and output_ref is not None
            # The digest in the row commits to the ciphertext on disk.
            blob = (led.dir / "blobs" / input_ref).read_bytes()
            assert hashlib.sha256(blob).hexdigest() == input_digest.hex()
            # Round-trip through the ledger's decryptor.
            assert led.read_blob(input_ref, key_id) == b"write the handler"

    def test_secrets_redacted_before_persistence(self, tmp_path):
        with Ledger(tmp_path / "ledger", EphemeralSigningKeyProvider()) as led:
            led.append(
                make_entry(1, input='token = "ghp_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0"')
            )
            ref, key_id = led.conn.execute(
                "SELECT input_ref, blob_key_id FROM ledger_entry WHERE seq = 1"
            ).fetchone()
            plaintext = led.read_blob(ref, key_id)
            assert b"ghp_a1B2c3D4" not in plaintext
            assert b"[REDACTED]" in plaintext

    def test_wrapped_keys_survive_reopen(self, tmp_path):
        # The blob master derives from the provisioned signing seed, so a
        # fixed seed (production: SecretStorage) unwraps across restarts;
        # an ephemeral signer has an equally ephemeral master by design.
        from meridian_core.ledger import ProvisionedSigningKeyProvider

        seed = bytes(range(32))
        ledger_dir = tmp_path / "ledger"
        with Ledger(ledger_dir, ProvisionedSigningKeyProvider(seed)) as led:
            led.append(
                make_entry(1, input="persist me", blob_subject="subject-a")
            )
            ref, key_id = led.conn.execute(
                "SELECT input_ref, blob_key_id FROM ledger_entry WHERE seq = 1"
            ).fetchone()
        with Ledger(ledger_dir, ProvisionedSigningKeyProvider(seed)) as led:
            # WrappedBlobKeyStore unwraps the persisted key — no raw key
            # material on disk, but the subject key survives.
            assert led.read_blob(ref, key_id) == b"persist me"

    def test_crypto_shredding_makes_blob_unreadable_not_the_chain(self, tmp_path):
        ledger_dir = tmp_path / "ledger"
        with Ledger(ledger_dir, EphemeralSigningKeyProvider()) as led:
            led.append(make_entry(1, input="personal data", blob_subject="subj-1"))
            led.append(make_entry(2, input="unrelated", blob_subject="subj-2"))
            ref, key_id = led.conn.execute(
                "SELECT input_ref, blob_key_id FROM ledger_entry WHERE seq = 1"
            ).fetchone()
            assert led.shred_subject("subj-1") is True
            with pytest.raises(BlobKeyMissing):
                led.read_blob(ref, key_id)
            # No row deleted; the other subject is unaffected.
            assert led.conn.execute("SELECT COUNT(*) FROM ledger_entry").fetchone()[0] == 2
            ref2, key2 = led.conn.execute(
                "SELECT input_ref, blob_key_id FROM ledger_entry WHERE seq = 2"
            ).fetchone()
            assert led.read_blob(ref2, key2) == b"unrelated"
            # Double-shred is a no-op, not an error.
            assert led.shred_subject("subj-1") is False
