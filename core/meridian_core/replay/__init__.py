"""Cassettes — M27 record/replay, AC-15.

A cassette captures one story's ledger exactly: every row (hash columns
included), every referenced blob's ciphertext, and the signing seed. A
byte-identical chain is only meaningful over RECORDED values — the blob
store deliberately uses random nonces (a security property, not a
defect), so re-encrypting plaintext on replay could never reproduce the
recorded ciphertext digests the chain commits to. The cassette is
therefore a self-contained replayable artifact: replay restores rows
and blob ciphertext verbatim, rebuilds the Merkle frontier, and proves
the chain with ``Ledger.verify()``. Tampering with any recorded byte
fails verification — which is what AC-15's golden runner needs.

Cassette layout (JSON):
    version, storyId, signingSeedHex,
    columns: [...],            # ledger_entry column order
    rows: [[...], ...],        # values; BLOBs hex-encoded
    blobs: {ref: hex-bytes},   # ciphertext, content-addressed
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from meridian_core.ledger import Ledger, ProvisionedSigningKeyProvider

CASSETTE_VERSION = 1
_HASH_COLUMNS = ("prev_hash", "entry_hash")


class CassetteError(ValueError):
    """A cassette violated its determinism or integrity rules."""


@dataclass(frozen=True)
class Cassette:
    story_id: str
    signing_seed_hex: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    blobs: Mapping[str, str]  # ref -> ciphertext hex
    #: Wrapped blob keys (master-key-wrapped, so safe to carry — the
    #: master derives from the cassette's signing seed). Without them a
    #: replayed ledger could not decrypt the replayed ciphertext.
    keys: tuple[tuple[str, str, str, str], ...] = ()  # key_id, subject, wrapped hex, created

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CASSETTE_VERSION,
            "storyId": self.story_id,
            "signingSeedHex": self.signing_seed_hex,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "blobs": dict(self.blobs),
            "keys": [list(k) for k in self.keys],
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> "Cassette":
        if raw.get("version") != CASSETTE_VERSION:
            raise CassetteError(
                f"cassette schema version {raw.get('version')!r} is not"
                f" supported (this runner understands v{CASSETTE_VERSION})"
            )
        return Cassette(
            story_id=str(raw["storyId"]),
            signing_seed_hex=str(raw["signingSeedHex"]),
            columns=tuple(raw["columns"]),
            rows=tuple(tuple(row) for row in raw["rows"]),
            blobs={str(k): str(v) for k, v in (raw.get("blobs") or {}).items()},
            keys=tuple(tuple(k) for k in (raw.get("keys") or ())),
        )

    def save(self, path: Path) -> Path:
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        return path

    @staticmethod
    def load(path: Path) -> "Cassette":
        return Cassette.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _encode(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$blob": value.hex()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and "$blob" in value:
        return bytes.fromhex(value["$blob"])
    return value


def record_cassette(
    source: Ledger,
    *,
    story_id: str,
    signing_seed: bytes,
) -> Cassette:
    """Capture the source ledger's full chain and blob ciphertexts."""
    cursor = source.conn.execute("SELECT * FROM ledger_entry ORDER BY seq")
    columns = tuple(d[0] for d in cursor.description)
    rows = tuple(
        tuple(_encode(value) for value in row) for row in cursor.fetchall()
    )
    blobs: dict[str, str] = {}
    keys = tuple(
        (str(k), str(sub), bytes(w).hex(), str(c))
        for k, sub, w, c in source.conn.execute(
            "SELECT key_id, subject_id, wrapped_key, created_at FROM blob_key"
        ).fetchall()
    )
    blob_root = source._blobs._root  # package-internal, same package family
    for column in ("input_ref", "output_ref"):
        if column not in columns:
            continue
        index = columns.index(column)
        for row in rows:
            ref = row[index]
            if not ref:
                continue
            blob_path = blob_root / str(ref)
            if blob_path.is_file() and str(ref) not in blobs:
                blobs[str(ref)] = blob_path.read_bytes().hex()
    return Cassette(
        story_id=story_id,
        signing_seed_hex=signing_seed.hex(),
        columns=columns,
        rows=rows,
        blobs=blobs,
        keys=keys,
    )


def replay_cassette(cassette: Cassette, destination: Path) -> Ledger:
    """AC-15: restore the recorded chain into a fresh ledger and prove
    it. Any tamper with a recorded row or blob fails here — verification
    is the contract, not best-effort equality."""
    ledger = Ledger(
        destination,
        ProvisionedSigningKeyProvider(bytes.fromhex(cassette.signing_seed_hex)),
    )
    try:
        blob_root = ledger._blobs._root
        blob_root.mkdir(parents=True, exist_ok=True)
        for key_id, subject, wrapped_hex, created in cassette.keys:
            ledger.conn.execute(
                "INSERT OR IGNORE INTO blob_key (key_id, subject_id,"
                " wrapped_key, created_at) VALUES (?, ?, ?, ?)",
                (key_id, subject, bytes.fromhex(wrapped_hex), created),
            )
        for ref, hex_bytes in cassette.blobs.items():
            path = blob_root / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes.fromhex(hex_bytes))
        for raw_row in cassette.rows:
            row = {col: _decode(val) for col, val in zip(cassette.columns, raw_row)}
            columns = ", ".join(cassette.columns)
            ledger.conn.execute(
                f"INSERT INTO ledger_entry ({columns}) VALUES"
                f" ({', '.join('?' for _ in cassette.columns)})",
                [row[col] for col in cassette.columns],
            )
            ledger._frontier.append(row["entry_hash"])
            ledger._last_seq = int(row["seq"])
            ledger._last_hash = row["entry_hash"]
        ledger.conn.commit()
        if not ledger.verify().ok:
            ledger.close()
            raise CassetteError(
                "AC-15: replayed cassette failed chain verification — the"
                " recording was tampered with or is corrupt"
            )
        return ledger
    except Exception:
        ledger.close()
        raise
