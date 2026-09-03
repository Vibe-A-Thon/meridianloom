"""FR-M10 provenance ledger: append-only, hash-chained, Merkle-signed.

Submodules:
- schema — normative §7.2 DDL, append-only triggers, migrations (FR-M10-01)
- canonical — canonical JSON and entry hashing (FR-M10-02)
- merkle — Merkle tree, inclusion/consistency proofs (FR-M10-03)
- keys — signing key provider + tree-head signatures (FR-M10-04)
- keystore — per-subject blob keys, wrapped at rest (FR-M10-14)
- blobs — encrypted content-addressed blob store (FR-M10-07)
- redaction — SEC-07 secret filter applied before persistence
- range_verify — FR-M10-09 parallel-verification worker (light imports)
- wire — bus (camelCase) <-> ledger (snake_case) mapping
- core — the Ledger facade: append, query, verify, tree heads

Imports are lazy so multiprocessing spawn children (range_verify) load
only what they need — never the cryptography stack.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = {
    "schema": "schema",
    "canonical": "canonical",
    "merkle": "merkle",
    "keys": "keys",
    "keystore": "keystore",
    "blobs": "blobs",
    "redaction": "redaction",
    "range_verify": "range_verify",
    "wire": "wire",
    "core": "core",
}

_EXPORTS = {
    "SCHEMA_VERSION": "schema",
    "GENESIS_HASH": "canonical",
    "Ledger": "core",
    "AppendResult": "core",
    "VerifyResult": "core",
    "MerkleFrontier": "merkle",
    "SigningKeyProvider": "keys",
    "EphemeralSigningKeyProvider": "keys",
    "ProvisionedSigningKeyProvider": "keys",
    "BlobKeyStore": "keystore",
    "EphemeralBlobKeyStore": "keystore",
    "WrappedBlobKeyStore": "keystore",
    "BlobStore": "blobs",
    "BlobError": "blobs",
    "BlobKeyMissing": "blobs",
    "BlobNotFound": "blobs",
    "BlobTampered": "blobs",
    "canonical_json": "canonical",
    "entry_hash": "canonical",
    "hashable_payload": "canonical",
    "make_verify_hasher": "canonical",
    "sign_tree_head": "keys",
    "verify_tree_head": "keys",
    "derive_blob_master_key": "keystore",
    "key_id_for": "keystore",
    "redact_secrets": "redaction",
    "inclusion_proof": "merkle",
    "consistency_proof": "merkle",
    "verify_inclusion": "merkle",
    "verify_consistency": "merkle",
    "apply_migrations": "schema",
    "connect": "schema",
}

#: Aliased exports: name -> (module, attribute in that module).
_ALIASES = {
    "merkle_root": ("merkle", "root"),
}

__all__ = sorted([*_SUBMODULES, *_EXPORTS, *_ALIASES])


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    if name in _EXPORTS:
        module = importlib.import_module(f".{_EXPORTS[name]}", __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    if name in _ALIASES:
        module_name, attribute = _ALIASES[name]
        module = importlib.import_module(f".{module_name}", __name__)
        value = getattr(module, attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
