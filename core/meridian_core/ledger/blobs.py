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
import re
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


class BlobRefInvalid(BlobError):
    """A blob reference is not the shape this store issues.

    Refs are content-addressed and fully determined: two hex characters of
    the digest, a separator, the full digest, ``.blob``. Nothing else is
    ever produced, so anything else is either corruption or an attempt to
    steer a file write, and both are refused the same way.
    """


#: The only shape a ref may take. An allow-list rather than a hunt for
#: ``..``, because the set of ways to escape a directory is open-ended
#: (``..``, absolute paths, ``C:`` drive-relative paths, UNC roots, NUL
#: truncation) while the set of valid refs is exactly this.
_REF_PATTERN = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{64}\.blob$")


def normalise_ref(ref: str) -> str:
    """Validate a blob ref and return it in posix form.

    Refs reach this process from three places, and two of them are outside
    its control: rows in a ledger database that may have been restored from
    a backup, and ``manifest.json`` files in customer-controlled cold
    storage. Both are joined onto a root and written to
    (``mkdir(parents=True)`` then ``write_bytes``), so a ref of
    ``../../../x`` was an arbitrary-file write, and an absolute ref replaced
    the root outright. The digest checks downstream do not help: they
    constrain the *content* written, never the path.

    Backslash separators are accepted and converted. Older archives carry
    them because the ref used to be built with ``str(Path.relative_to(...))``,
    which emits the local separator — so an archive written on Windows named
    a file no POSIX machine could find, and cold storage meant to be handed
    to an auditor was not portable between them.
    """
    candidate = str(ref).replace("\\", "/")
    if not _REF_PATTERN.match(candidate):
        raise BlobRefInvalid(f"not a blob reference: {ref!r}")
    return candidate


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
        return digest_hex, f"{digest_hex[:2]}/{digest_hex}{SUFFIX}"

    def get(self, ref: str, blob_key_id: str) -> bytes:
        raw_key = self._keys.get(blob_key_id)
        if raw_key is None:
            raise BlobKeyMissing(f"no key for {blob_key_id}")
        path = self._root / normalise_ref(ref)
        if not path.is_file():
            raise BlobNotFound(ref)
        blob = path.read_bytes()
        nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
        try:
            return AESGCM(raw_key).decrypt(nonce, ciphertext, AAD)
        except InvalidTag as error:
            raise BlobTampered(ref) from error
