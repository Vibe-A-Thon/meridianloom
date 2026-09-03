"""FR-M10-04 / SEC-06: signing-key provisioning and tree-head signatures.

The Ed25519 signing key lives in the OS keychain (the extension host's
SecretStorage, FR-M1-06) and is provisioned to the sidecar inside the
stdio handshake as a 32-byte seed. Key material is held in memory only:
it is never written to disk and never stored in the ledger — the ledger
holds signatures and public keys, both safe to publish (SEC-29).

When no seed is provisioned the sidecar falls back to an ephemeral key
and doctor reports it: tree heads are still signed (integrity semantics
intact for the session), but the signer identity does not survive a
restart.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from .canonical import canonical_json

SEED_BYTES = 32
SIGNING_ALGORITHM = "Ed25519"


@runtime_checkable
class SigningKeyProvider(Protocol):
    """Source of the ledger's Ed25519 signing key (memory-resident only)."""

    def private_key(self) -> Ed25519PrivateKey: ...


class ProvisionedSigningKeyProvider:
    """Wraps a 32-byte seed provisioned over the handshake from SecretStorage."""

    def __init__(self, seed: bytes) -> None:
        if len(seed) != SEED_BYTES:
            raise ValueError(f"Ed25519 seed must be {SEED_BYTES} bytes")
        self._key = Ed25519PrivateKey.from_private_bytes(seed)

    def private_key(self) -> Ed25519PrivateKey:
        return self._key


class EphemeralSigningKeyProvider:
    """Generates a throwaway key per process; used in tests and as the
    unprovisioned fallback (doctor flags the missing keychain key)."""

    def __init__(self) -> None:
        self._key = Ed25519PrivateKey.generate()

    def private_key(self) -> Ed25519PrivateKey:
        return self._key


def public_key_bytes(key: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    public = key if isinstance(key, Ed25519PublicKey) else key.public_key()
    return public.public_bytes(Encoding.Raw, PublicFormat.Raw)


def tree_head_message(seq: int, root_hash: bytes, signed_at: str) -> bytes:
    """Canonical bytes an FR-M10-04 tree-head signature commits to."""
    return canonical_json(
        {"root_hash": root_hash.hex(), "seq": seq, "signed_at": signed_at}
    )


def sign_tree_head(
    provider: SigningKeyProvider, seq: int, root_hash: bytes, signed_at: str
) -> bytes:
    return provider.private_key().sign(tree_head_message(seq, root_hash, signed_at))


def verify_tree_head(
    public_key: bytes,
    seq: int,
    root_hash: bytes,
    signed_at: str,
    signature: bytes,
) -> bool:
    """Verify a signed tree head with only the public key (SEC-29)."""
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, tree_head_message(seq, root_hash, signed_at)
        )
    except (InvalidSignature, ValueError):
        return False
    return True
