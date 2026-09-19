"""Mint licences for tests with a throwaway development key.

Nothing here can produce a licence the shipped product would accept: the key
is generated fresh, and the product only trusts a development key when it is
running from a source checkout *and* ``MERIDIAN_DEV_LICENCE_TRUST_FILE`` names
it (see ``meridian_core/licensing/keys.py``).

Also usable as a script, so the extension's vitest suite can obtain the two
environment variables its real-sidecar tests need::

    python core/tests/licensing_support.py <output-dir>     # prints JSON env
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian_core.licensing import licence as lic  # noqa: E402

DEV_KEY_ID = "ml-dev"


class DevIssuer:
    def __init__(self, key_id: str = DEV_KEY_ID) -> None:
        self.key_id = key_id
        self._key = Ed25519PrivateKey.generate()
        self.public_bytes = self._key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    @property
    def public_b64(self) -> str:
        return base64.b64encode(self.public_bytes).decode("ascii")

    def trusted(self, development: bool = True) -> dict[str, lic.TrustedKey]:
        return {self.key_id: lic.TrustedKey(self.key_id, self.public_bytes, development)}

    def payload(self, **overrides: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "licenceId": "ML-TEST-0001",
            "product": lic.PRODUCT,
            "edition": lic.EDITION_PREMIUM,
            "licensee": {"name": "Test Licensee Ltd", "contact": "it@test.example"},
            "kind": lic.KIND_MACHINE,
            "bindings": {"machines": ["*"]},
            "seats": 1,
            "features": ["*"],
            "issuedAt": lic.format_time(now - timedelta(days=1)),
            "expiresAt": lic.format_time(now + timedelta(days=3650)),
            "trial": False,
        }
        payload.update(overrides)
        return payload

    def issue(self, key_id: str | None = None, **overrides: Any) -> str:
        return self.sign(self.payload(**overrides), key_id)

    def sign(self, payload: dict[str, Any], key_id: str | None = None) -> str:
        signature = self._key.sign(lic.canonical_payload(payload))
        document = {
            "format": lic.FORMAT,
            "payload": payload,
            "signature": {
                "alg": "Ed25519",
                "keyId": key_id or self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        return json.dumps(document, indent=2, sort_keys=True) + "\n"


def make_dev_licence_files(directory: Path) -> dict[str, str]:
    """Write a development public key and an all-features wildcard licence;
    return the environment variables that make a *source-checkout* sidecar
    honour them."""
    directory.mkdir(parents=True, exist_ok=True)
    issuer = DevIssuer()
    trust = directory / "dev-public.key"
    licence = directory / "dev-premium.mlic"
    trust.write_text(issuer.public_b64 + "\n", encoding="ascii")
    licence.write_text(issuer.issue(), encoding="utf-8")
    return {
        "MERIDIAN_DEV_LICENCE_TRUST_FILE": str(trust),
        "MERIDIAN_LICENCE_FILE": str(licence),
    }


if __name__ == "__main__":
    print(json.dumps(make_dev_licence_files(Path(sys.argv[1]))))
