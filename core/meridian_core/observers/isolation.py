"""One-way isolation helpers (SEC-27).

Observed agents must never gain access to Meridian credentials, policy, or
the ledger signing key. Every process the observer subsystem spawns (gh
probes, process-listing probes) runs with a scrubbed environment: every
``MERIDIAN_*`` variable is removed, and the removal is AUDITED — the
caller gets the list of what was stripped, so a test can assert no secret
crossed the boundary.

The observer subsystem never loads key material: nothing under
``meridian_core.observers`` imports ``meridian_core.ledger`` (enforced by
test_observer_isolation.py). Pure stdlib; zero model calls (FR-M36-07).
"""

from __future__ import annotations

import os
from typing import Mapping

SECRET_ENV_PREFIX = "MERIDIAN_"


def scrub_env(
    env: Mapping[str, str] | None = None,
    allowlist: tuple[str, ...] = (),
) -> tuple[dict[str, str], list[str]]:
    """Return (clean_env, scrubbed_keys_audit) with MERIDIAN_* removed.

    ``env`` defaults to ``os.environ`` — i.e. the caller's full secret
    environment. Nothing starting with MERIDIAN_ crosses into a spawned
    probe unless explicitly allowlisted (today: nothing is).
    """
    source = dict(os.environ if env is None else env)
    clean: dict[str, str] = {}
    scrubbed: list[str] = []
    for key, value in source.items():
        if key.startswith(SECRET_ENV_PREFIX) and key not in allowlist:
            scrubbed.append(key)
            continue
        clean[key] = value
    return clean, sorted(scrubbed)
