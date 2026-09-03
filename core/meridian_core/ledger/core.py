"""The Ledger facade: append with hash-chain + Merkle + signed tree heads.

FR-M10-02: every entry chains `prev_hash -> entry_hash`.
FR-M10-03: a Merkle tree (frontier) is maintained over entries; roots
are reproducible as RFC 6962 tree hashes.
FR-M10-04: signed tree heads are emitted at a configurable cadence
(default: every 100 entries or 10 minutes), Ed25519 over the canonical
head, key memory-resident (keys.py).
FR-M10-08: append commits (WAL, synchronous=FULL) before returning —
see tests for the kill -9 durability proof.

Query/verify/proof/export surfaces land in later tasks (FR-M10-09/12,
FR-M11-01..05) and hang off this class.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import canonical, keys, merkle, schema
from .blobs import BlobStore
from .keystore import (
    BlobKeyStore,
    WrappedBlobKeyStore,
    derive_blob_master_key,
    key_id_for,
)
from .redaction import redact_secrets

# Columns that must be present in every append() call (NOT NULL, no default).
REQUIRED_FIELDS = frozenset(
    {
        "story_id",
        "phase",
        "loop_id",
        "loop_iteration",
        "actor_id",
        "actor_version",
        "actor_kind",
        "policy_version",
        "action_type",
    }
)

DEFAULTS: dict[str, Any] = {
    "vendor": "meridian",
    "observation_confidence": "direct",
    "simulated": 0,
}

TREE_HEAD_INTERVAL_ENTRIES = 100
TREE_HEAD_MAX_AGE_S = 600


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class AppendResult:
    sequence: int
    ts_utc: str
    prev_hash: bytes
    entry_hash: bytes
    tree_head: dict[str, Any] | None


class Ledger:
    """An open ledger database. Not thread-safe; the sidecar serialises."""

    def __init__(
        self,
        ledger_dir: Path,
        signing_key: keys.SigningKeyProvider,
        *,
        tree_head_interval: int = TREE_HEAD_INTERVAL_ENTRIES,
        tree_head_max_age_s: float = TREE_HEAD_MAX_AGE_S,
        blob_key_store: BlobKeyStore | None = None,
    ) -> None:
        self.dir = Path(ledger_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._signing_key = signing_key
        self._tree_head_interval = tree_head_interval
        self._tree_head_max_age_s = tree_head_max_age_s
        self.conn = schema.connect(self.dir / "ledger.db")
        schema.apply_migrations(self.conn)

        # FR-M10-07: blobs live beside the database; per-subject keys come
        # from the wrapped registry unless a caller injects a store (tests).
        self._blob_keys = blob_key_store or WrappedBlobKeyStore(
            self.conn,
            derive_blob_master_key(
                signing_key.private_key().private_bytes_raw()
            ),
        )
        self._blobs = BlobStore(self.dir / "blobs", self._blob_keys)

        self._columns: tuple[str, ...] = tuple(
            row[1]
            for row in self.conn.execute("PRAGMA table_info(ledger_entry)")
        )
        unknown_hashable = canonical.HASH_EXCLUDED_COLUMNS - set(self._columns)
        if unknown_hashable:
            raise RuntimeError(f"schema drift: {unknown_hashable} not in table")

        self._frontier = merkle.MerkleFrontier()
        last = self.conn.execute(
            "SELECT seq, entry_hash FROM ledger_entry ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self._last_seq: int = last[0] if last else 0
        self._last_hash: bytes = last[1] if last else canonical.GENESIS_HASH
        for (entry_hash,) in self.conn.execute(
            "SELECT entry_hash FROM ledger_entry ORDER BY seq"
        ):
            self._frontier.append(entry_hash)

        head = self.conn.execute(
            "SELECT seq FROM tree_head ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        self._last_head_seq: int = head[0] if head else 0
        self._head_opened_monotonic = time.monotonic()

    # -- state -------------------------------------------------------------

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @property
    def last_sequence(self) -> int:
        return self._last_seq

    @property
    def signing_public_key(self) -> bytes:
        return keys.public_key_bytes(self._signing_key.private_key())

    def root_hash(self) -> bytes:
        return self._frontier.root()

    # -- append (FR-M10-02/07/08) -------------------------------------------

    def append(self, entry: dict[str, Any]) -> AppendResult:
        """Append one entry; the chain update is committed before returning.

        `entry` carries the normative columns. Two conveniences on top:
        `input` / `output` (str or bytes) are secret-redacted (SEC-07),
        encrypted and content-addressed into the blob store before the row
        is written; `blob_subject` selects the per-subject key (defaults
        to the caller-supplied `blob_key_id`, else "default").
        """
        entry = dict(entry)
        input_data = entry.pop("input", None)
        output_data = entry.pop("output", None)
        blob_subject = entry.pop("blob_subject", None)
        row = self._prepare_row(entry)
        if input_data is not None or output_data is not None:
            self._attach_blobs(row, input_data, output_data, blob_subject)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            prev_hash = self._last_hash
            row.update(
                seq=self._last_seq + 1,
                ts_utc=row.get("ts_utc") or utc_now(),
                prev_hash=prev_hash,
            )
            row["entry_hash"] = canonical.entry_hash(prev_hash, row)
            columns = list(row)
            self.conn.execute(
                f"INSERT INTO ledger_entry ({', '.join(columns)})"
                f" VALUES ({', '.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        self._frontier.append(row["entry_hash"])
        self._last_seq = row["seq"]
        self._last_hash = row["entry_hash"]
        return AppendResult(
            sequence=row["seq"],
            ts_utc=row["ts_utc"],
            prev_hash=prev_hash,
            entry_hash=row["entry_hash"],
            tree_head=self._maybe_emit_tree_head(),
        )

    def _attach_blobs(
        self,
        row: dict[str, Any],
        input_data: Any,
        output_data: Any,
        blob_subject: str | None,
    ) -> None:
        if isinstance(input_data, str):
            input_data = redact_secrets(input_data).encode("utf-8")
        if isinstance(output_data, str):
            output_data = redact_secrets(output_data).encode("utf-8")
        key_id = row.get("blob_key_id")
        if key_id is None:
            key_id = self._blob_keys.key_for(blob_subject or "default")
            row["blob_key_id"] = key_id
        for prefix, data in (("input", input_data), ("output", output_data)):
            if data is None:
                continue
            digest, ref = self._blobs.put(data, key_id)
            row[f"{prefix}_digest"] = bytes.fromhex(digest)
            row[f"{prefix}_ref"] = ref

    # -- blobs (FR-M10-07/14) -----------------------------------------------

    def read_blob(self, ref: str, blob_key_id: str) -> bytes:
        """Decrypt a referenced blob; raises when the key was shredded."""
        return self._blobs.get(ref, blob_key_id)

    def shred_subject(self, subject_id: str) -> bool:
        """FR-M10-14 groundwork: destroy a subject's blob key.

        Rows stay, the chain still verifies (it hashes ciphertext), the
        blobs become unreadable. The erasure-event ledger entry lands
        with the full crypto-shredding flow in F4.
        """
        return self._blob_keys.destroy(key_id_for(subject_id))

    def _prepare_row(self, entry: dict[str, Any]) -> dict[str, Any]:
        unknown = set(entry) - set(self._columns) - {"ts_utc"}
        if unknown:
            raise ValueError(f"unknown entry fields: {sorted(unknown)}")
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(f"missing required fields: {sorted(missing)}")
        row: dict[str, Any] = {}
        for column in self._columns:
            if column == "seq":
                continue  # assigned at insert time
            value = entry.get(column, DEFAULTS.get(column))
            if column == "simulated" and isinstance(value, bool):
                value = int(value)
            row[column] = value
        if row["observation_confidence"] not in ("direct", "telemetry", "inferred"):
            raise ValueError("observation_confidence must be direct|telemetry|inferred")
        if row.get("origin") is not None and row["origin"] not in (
            "ui", "command", "omnibar", "chat", "editor", "file", "connector", "api",
        ):
            raise ValueError("origin must be one of the FR-M40-02 doors or null")
        return row

    # -- signed tree heads (FR-M10-04) --------------------------------------

    def _maybe_emit_tree_head(self) -> dict[str, Any] | None:
        age = time.monotonic() - self._head_opened_monotonic
        due = (
            self._last_seq - self._last_head_seq >= self._tree_head_interval
            or age >= self._tree_head_max_age_s
        )
        if not due:
            return None
        signed_at = utc_now()
        root = self._frontier.root()
        signature = keys.sign_tree_head(
            self._signing_key, self._last_seq, root, signed_at
        )
        self.conn.execute(
            "INSERT INTO tree_head (seq, root_hash, signed_at, signature)"
            " VALUES (?, ?, ?, ?)",
            (self._last_seq, root, signed_at, signature),
        )
        self.conn.commit()
        self._last_head_seq = self._last_seq
        self._head_opened_monotonic = time.monotonic()
        return {
            "seq": self._last_seq,
            "root_hash": root.hex(),
            "signed_at": signed_at,
            "signature": signature.hex(),
        }

    def tree_heads(self) -> list[sqlite3.Row | Any]:
        return self.conn.execute(
            "SELECT seq, root_hash, signed_at, signature, anchor_ref"
            " FROM tree_head ORDER BY seq"
        ).fetchall()
