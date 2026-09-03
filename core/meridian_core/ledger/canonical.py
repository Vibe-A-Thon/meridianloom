"""FR-M10-02: canonical serialisation and the entry hash chain.

Canonicalisation (normative, Requirements_Final.md §7.2): JSON with keys
sorted lexicographically, UTF-8, no insignificant whitespace; `prev_hash`
and `entry_hash` are excluded from the hashed payload; digests are
hex-encoded lowercase. The chain binds each entry to its predecessor:

    entry_hash(n) = SHA-256( prev_hash(n) || canonical_payload(n) )

with prev_hash(1) defined as 32 zero bytes (the genesis link). The raw
previous hash bytes are prepended before serialisation so the link cannot
be re-pointed without changing the digest.

The open ledger specification (FR-M36-06, F0-E task 27) must describe
this exact construction; float serialisation follows Python's
`json.dumps` shortest-repr rule, which the spec will need to pin down.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Columns excluded from the hashed payload (§7.2). Everything else —
# including seq — is bound into the entry hash.
HASH_EXCLUDED_COLUMNS = frozenset({"prev_hash", "entry_hash"})

#: prev_hash of sequence 1: the genesis link.
GENESIS_HASH = b"\x00" * 32


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Canonical JSON bytes per §7.2. NaN/Infinity are refused outright."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def hashable_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Project a ledger row onto its hashable payload.

    Bytes (digests, signatures) become lowercase hex strings; everything
    else passes through as JSON-native values.
    """
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if key in HASH_EXCLUDED_COLUMNS:
            continue
        if isinstance(value, (bytes, bytearray, memoryview)):
            payload[key] = bytes(value).hex()
        else:
            payload[key] = value
    return payload


def entry_hash(prev_hash: bytes, row: dict[str, Any]) -> bytes:
    """SHA-256 over (prev_hash, canonical entry content) — FR-M10-02."""
    digest = hashlib.sha256()
    digest.update(prev_hash)
    digest.update(canonical_json(hashable_payload(row)))
    return digest.digest()
