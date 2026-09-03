"""FR-M10-14 groundwork: per-subject blob-key store.

Every subject (a story, an external session, a human) gets its own
random AES-256 key, so crypto-shredding later is destroying one key, not
rewriting history. Keys are never stored raw: each is wrapped (AES-GCM)
under a workspace master key and persisted in the `blob_key` table. Raw
key material appears only in memory — never on disk, never in the ledger.

The master key is derived (HKDF-SHA256, domain-separated) from the
provisioned signing seed, so no second keychain entry is needed; with an
ephemeral signer the master is equally ephemeral and doctor reports it.

The key registry is deliberately NOT append-only: erasure destroys the
wrapped key row (the FR-M10-01 carve-out covers key destruction, not
row deletion — the ledger rows and chain stay intact).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MASTER_KEY_BYTES = 32
BLOB_KEY_BYTES = 32
_WRAPPED_NONCE_BYTES = 12
HKDF_INFO = b"meridian/blob-master/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def key_id_for(subject_id: str) -> str:
    return f"bk:{subject_id}"


@runtime_checkable
class BlobKeyStore(Protocol):
    """Resolve, create and destroy per-subject blob keys."""

    def key_for(self, subject_id: str) -> str:
        """Return the blob_key_id for the subject (created if absent)."""
        ...

    def get(self, blob_key_id: str) -> bytes | None:
        """Raw key bytes, or None when unknown or crypto-shredded."""
        ...

    def destroy(self, blob_key_id: str) -> bool:
        """Crypto-shred: delete the wrapped key. Returns True if it existed."""
        ...


def derive_blob_master_key(signing_private_bytes: bytes) -> bytes:
    """Workspace master key, HKDF-derived from the provisioned seed."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=MASTER_KEY_BYTES,
        salt=None,
        info=HKDF_INFO,
    ).derive(signing_private_bytes)


class WrappedBlobKeyStore:
    """Persistent store: per-subject keys wrapped under the master key."""

    def __init__(self, conn: sqlite3.Connection, master_key: bytes) -> None:
        if len(master_key) != MASTER_KEY_BYTES:
            raise ValueError(f"master key must be {MASTER_KEY_BYTES} bytes")
        self._conn = conn
        self._aead = AESGCM(master_key)

    def key_for(self, subject_id: str) -> str:
        key_id = key_id_for(subject_id)
        if self.get(key_id) is not None:
            return key_id
        raw = os.urandom(BLOB_KEY_BYTES)
        nonce = os.urandom(_WRAPPED_NONCE_BYTES)
        self._conn.execute(
            "INSERT INTO blob_key (key_id, subject_id, wrapped_key, created_at)"
            " VALUES (?, ?, ?, ?)",
            (key_id, subject_id, nonce + self._aead.encrypt(nonce, raw, key_id.encode()), utc_now()),
        )
        self._conn.commit()
        return key_id

    def get(self, blob_key_id: str) -> bytes | None:
        row = self._conn.execute(
            "SELECT wrapped_key FROM blob_key WHERE key_id = ?", (blob_key_id,)
        ).fetchone()
        if row is None:
            return None
        wrapped = row[0]
        nonce, ciphertext = wrapped[:_WRAPPED_NONCE_BYTES], wrapped[_WRAPPED_NONCE_BYTES:]
        return self._aead.decrypt(nonce, ciphertext, blob_key_id.encode())

    def destroy(self, blob_key_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM blob_key WHERE key_id = ?", (blob_key_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0


class EphemeralBlobKeyStore:
    """In-memory keys for tests and unprovisioned fallbacks."""

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def key_for(self, subject_id: str) -> str:
        key_id = key_id_for(subject_id)
        self._keys.setdefault(key_id, os.urandom(BLOB_KEY_BYTES))
        return key_id

    def get(self, blob_key_id: str) -> bytes | None:
        return self._keys.get(blob_key_id)

    def destroy(self, blob_key_id: str) -> bool:
        return self._keys.pop(blob_key_id, None) is not None
