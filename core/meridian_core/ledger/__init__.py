"""FR-M10 provenance ledger: append-only, hash-chained, Merkle-signed.

Submodules:
- schema — normative §7.2 DDL, append-only triggers, migrations (FR-M10-01)
- canonical — canonical JSON and entry hashing (FR-M10-02)
- merkle — Merkle tree, inclusion/consistency proofs (FR-M10-03)
- keys — signing key provider + per-subject blob key store (FR-M10-04/14)
- blobs — encrypted content-addressed blob store (FR-M10-07)
- core — the Ledger facade: append, query, verify, proofs (FR-M10-08/09/12)
"""

from .schema import SCHEMA_VERSION, apply_migrations, connect

__all__ = ["SCHEMA_VERSION", "apply_migrations", "connect"]
