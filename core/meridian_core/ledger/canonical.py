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

Performance (FR-M10-09): `make_verify_hasher` precompiles the payload
projection for a fixed column list so a 100k-entry verify re-encodes
each row with the C JSON encoder and no per-row key sorting. It must
produce byte-identical digests to `entry_hash` — asserted in tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

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


def make_verify_hasher(
    columns: list[str],
) -> Callable[[bytes, tuple[Any, ...]], bytes]:
    """Precompiled row hasher for the verification fast path.

    `columns` is the SELECT column order; `values` the fetched tuple.
    Emits exactly what entry_hash(prev_hash, dict(zip(columns, values)))
    would emit, without per-row key sorting or isinstance dispatch: the
    payload dict is built in canonical (sorted) order straight from the
    tuple, and only the known BLOB columns are hex-projected.
    """
    from operator import itemgetter

    blob_columns = {"input_digest", "output_digest", "signature"}
    hashed = [
        (column, index)
        for index, column in enumerate(columns)
        if column not in HASH_EXCLUDED_COLUMNS
    ]
    hashed.sort(key=lambda pair: pair[0])
    names = [column for column, _index in hashed]
    indices = [index for _column, index in hashed]
    pick = itemgetter(*indices)
    bytes_positions = [
        position
        for position, name in enumerate(names)
        if name in blob_columns
    ]
    # Byte-identical to canonical_json (names are pre-sorted; separators
    # and ensure_ascii match) with the pure-overhead flags off: no
    # re-sorting, no circular-reference tracking. This is the FR-M10-09
    # fast path; byte-identity is asserted in tests.
    dumps = json.dumps

    def hasher(prev_hash: bytes, values: tuple[Any, ...]) -> bytes:
        picked = pick(values)
        payload = dict(zip(names, picked))
        for position in bytes_positions:
            value = picked[position]
            if value is not None:
                payload[names[position]] = value.hex()
        digest = hashlib.sha256()
        digest.update(prev_hash)
        digest.update(
            dumps(
                payload,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
                check_circular=False,
            ).encode("utf-8")
        )
        return digest.digest()

    return hasher
