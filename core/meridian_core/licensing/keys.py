"""The public keys the product trusts to sign licences.

Only *public* keys live here. The matching private key is held by the licensor
and never enters this repository (see ``tools/licensing/README.md``).

Key rotation: add the new key beside the old one, ship a release, start
issuing with the new key, and retire the old key by adding its id to
``REVOKED_KEY_IDS`` once every licence signed with it has been re-issued.
Licences carry the id of the key that signed them, so old and new coexist.

**Development trust.** The test suite needs to mint licences without the
production private key. ``MERIDIAN_DEV_LICENCE_TRUST_FILE`` names a file that
holds a *development* public key; it is honoured **only when running from a
source checkout** (detected by the presence of ``shared/schema/tiers.json``
at the repository root above ``core/``, which the packaged VSIX never
contains). In an
installed product the variable does nothing, so it cannot be used to unlock
premium features on a customer machine.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from .licence import TrustedKey

#: keyId -> base64 raw 32-byte Ed25519 public key.
PRODUCTION_KEYS: dict[str, str] = {
    "ml-2026-1": "meTII9zTwpg+vvpGq4jm3J5ZaSRmrnBEzGkj2YSwEe4=",
}

#: Key ids whose licences are no longer accepted.
REVOKED_KEY_IDS: frozenset[str] = frozenset()

DEV_TRUST_ENV = "MERIDIAN_DEV_LICENCE_TRUST_FILE"
DEV_KEY_ID = "ml-dev"


def is_source_checkout() -> bool:
    """True only when this package sits in a development checkout."""
    here = Path(__file__).resolve()
    return (here.parents[3] / "shared" / "schema" / "tiers.json").is_file()


def _decode(public_key_b64: str) -> bytes | None:
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
    except (ValueError, TypeError):
        return None
    return raw if len(raw) == 32 else None


def trusted_keys() -> dict[str, TrustedKey]:
    keys: dict[str, TrustedKey] = {}
    for key_id, encoded in PRODUCTION_KEYS.items():
        raw = _decode(encoded)
        if raw is not None:
            keys[key_id] = TrustedKey(key_id=key_id, public_key=raw)
    dev_file = os.environ.get(DEV_TRUST_ENV)
    if dev_file and is_source_checkout():
        try:
            raw = _decode(Path(dev_file).read_text(encoding="ascii").strip())
        except OSError:
            raw = None
        if raw is not None:
            keys[DEV_KEY_ID] = TrustedKey(key_id=DEV_KEY_ID, public_key=raw, development=True)
    return keys
