"""Meridian Loom licensing: free Community edition, Premium by licence key.

* :mod:`.licence`  — the signed licence file: parse, verify, evaluate
* :mod:`.keys`     — the public keys the product trusts
* :mod:`.machine`  — the per-machine fingerprint
* :mod:`.editions` — which capabilities are free and which are Premium
* :mod:`.store`    — where licence files live; install and remove
* :mod:`.runtime`  — the manager the sidecar consults per request

Offline by design: a licence is verified against a public key that ships in
the product. Nothing is ever sent anywhere.
"""

from __future__ import annotations

from .licence import (  # noqa: F401
    ACTIVE_STATES,
    EDITION_COMMUNITY,
    EDITION_PREMIUM,
    FEATURES,
    GRACE_DAYS,
    Licence,
    LicenceError,
    LicenceStatus,
    NO_LICENCE,
)
from .runtime import LicenceManager, new_manager, set_test_status  # noqa: F401
