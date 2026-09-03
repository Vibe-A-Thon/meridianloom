"""FR-M10 provenance ledger: append-only, hash-chained, Merkle-signed.

Submodules:
- schema — normative §7.2 DDL, append-only triggers, migrations (FR-M10-01)
- canonical — canonical JSON and entry hashing (FR-M10-02)
- merkle — Merkle tree, inclusion/consistency proofs (FR-M10-03)
- keys — signing key provider + tree-head signatures (FR-M10-04)
- keystore — per-subject blob keys, wrapped at rest (FR-M10-14)
- blobs — encrypted content-addressed blob store (FR-M10-07)
- redaction — SEC-07 secret filter applied before persistence
- core — the Ledger facade: append, chain maintenance, tree heads
"""

from .canonical import GENESIS_HASH, canonical_json, entry_hash, hashable_payload
from .blobs import (
    BlobError,
    BlobKeyMissing,
    BlobNotFound,
    BlobStore,
    BlobTampered,
)
from .core import AppendResult, Ledger
from .keystore import (
    BlobKeyStore,
    EphemeralBlobKeyStore,
    WrappedBlobKeyStore,
    derive_blob_master_key,
    key_id_for,
)
from .keys import (
    EphemeralSigningKeyProvider,
    ProvisionedSigningKeyProvider,
    SigningKeyProvider,
    sign_tree_head,
    verify_tree_head,
)
from .merkle import (
    MerkleFrontier,
    consistency_proof,
    inclusion_proof,
    root as merkle_root,
    verify_consistency,
    verify_inclusion,
)
from .redaction import redact_secrets
from .schema import SCHEMA_VERSION, apply_migrations, connect

__all__ = [
    "SCHEMA_VERSION",
    "GENESIS_HASH",
    "Ledger",
    "AppendResult",
    "MerkleFrontier",
    "SigningKeyProvider",
    "EphemeralSigningKeyProvider",
    "ProvisionedSigningKeyProvider",
    "BlobKeyStore",
    "EphemeralBlobKeyStore",
    "WrappedBlobKeyStore",
    "BlobStore",
    "BlobError",
    "BlobKeyMissing",
    "BlobNotFound",
    "BlobTampered",
    "canonical_json",
    "entry_hash",
    "hashable_payload",
    "sign_tree_head",
    "verify_tree_head",
    "derive_blob_master_key",
    "key_id_for",
    "redact_secrets",
    "inclusion_proof",
    "consistency_proof",
    "verify_inclusion",
    "verify_consistency",
    "merkle_root",
    "apply_migrations",
    "connect",
]
