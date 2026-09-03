"""FR-M10-07: encrypted, content-addressed blob store.

Large payloads (prompts, outputs, diffs) are stored under
`.meridian/ledger/blobs/` with only their digest and reference in the
entry row. Each blob is encrypted with AES-256-GCM under the subject's
per-subject key (keystore.py) before addressing, so:

- the content address is the SHA-256 of the *ciphertext* — the chain
  (input_digest / output_digest) commits to ciphertext, and the FR-M10-01
  crypto-shredding carve-out holds: destroy a subject key and the blob is
  unreadable while every entry hash stays valid;
- the AES-GCM random nonce means identical plaintexts do not deduplicate —
  addressing is by content, not by plaintext.

Files are fsync'd before put() returns, so a blob referenced by a
committed entry cannot be a zero-length casualty of a kill -9
(FR-M10-08).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .keystore import BlobKeyStore

NONCE_BYTES = 12
AAD = b"meridian/blob/v1"
SUFFIX = ".blob"


class BlobError(Exception):
    """Base class for blob store failures."""


class BlobKeyMissing(BlobError):
    """The subject key is unknown or crypto-shredded: the blob is gone
    for good, exactly the FR-M10-14 guarantee."""


class BlobNotFound(BlobError):
    """The referenced ciphertext file does not exist."""


class BlobTampered(BlobError):
    """AES-GCM authentication failed: ciphertext was modified, or the
    wrong key was supplied."""


class BlobStore:
    def __init__(self, root: Path, keys: BlobKeyStore) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._keys = keys

    def _path_for(self, digest_hex: str) -> Path:
        return self._root / digest_hex[:2] / f"{digest_hex}{SUFFIX}"

    def put(self, plaintext: bytes, blob_key_id: str) -> tuple[str, str]:
        """Encrypt and store; return (digest hex of ciphertext, ref).

        The ref is the path relative to the blob root.
        """
        raw_key = self._keys.get(blob_key_id)
        if raw_key is None:
            raise BlobKeyMissing(f"no key for {blob_key_id}")
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = nonce + AESGCM(raw_key).encrypt(nonce, plaintext, AAD)
        digest_hex = hashlib.sha256(ciphertext).hexdigest()
        path = self._path_for(digest_hex)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(ciphertext)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        return digest_hex, str(path.relative_to(self._root))

    def get(self, ref: str, blob_key_id: str) -> bytes:
        raw_key = self._keys.get(blob_key_id)
        if raw_key is None:
            raise BlobKeyMissing(f"no key for {blob_key_id}")
        path = self._root / ref
        if not path.is_file():
            raise BlobNotFound(ref)
        blob = path.read_bytes()
        nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
        try:
            return AESGCM(raw_key).decrypt(nonce, ciphertext, AAD)
        except InvalidTag as error:
            raise BlobTampered(ref) from error
