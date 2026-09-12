"""The environment every process the sidecar spawns receives (SEC-27).

The sidecar's own environment can carry ``MERIDIAN_LEDGER_SIGNING_KEY`` — the
key that makes the ledger tamper-evident — and other ``MERIDIAN_*`` settings.
None of it belongs to the processes the sidecar starts, because most of those
run code that somebody else controls:

* **git** runs repository hooks, ``core.fsmonitor``, textconv and external
  diff drivers — code the repository's author wrote;
* the **engine runner** executes configured tools inside a sandbox directory,
  where a sandbox holding the signing key is not a sandbox;
* **language servers** load project configuration and plugins.

SEC-27 stripped these variables from observer probes and nowhere else. Every
other spawn inherited the full environment implicitly, so whenever a
``MERIDIAN_*`` secret was present in it — CI, a headless run, an operator who
exported one — a pre-commit hook in a repository Meridian committed to could
read it, and with the signing key forge ledger entries that still verify. A
negative control with a real hook saw the key on the old path and not on this
one.

To be precise about the exposure: the extension provisions the signing key
over the handshake and the sidecar holds it in memory, never reading it from
the environment, so a default install did not have it there to leak. The
defect was the rule — stated by SEC-27, enforced at two spawn sites and
silently absent at three — not a key known to have escaped.

So the rule lives here, once, and ``test_childenv.py`` refuses any spawn in
the package that does not pass an explicit environment.
"""

from __future__ import annotations

import os
from typing import Mapping

#: Nothing with this prefix crosses into a child process. Same prefix as
#: ``observers.isolation.SECRET_ENV_PREFIX``; the two are pinned together by
#: test.
SECRET_ENV_PREFIX = "MERIDIAN_"


def child_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """``os.environ`` without any ``MERIDIAN_*`` variable, plus ``extra``.

    Scrubbing is not emptying: ``PATH``, ``HOME``, ``SYSTEMROOT`` and the rest
    are how a child finds its own tools and configuration, and removing them
    would break every spawn rather than secure it.

    ``extra`` is applied last and may not reintroduce a scrubbed name — a
    caller that needs a Meridian setting inside a child has to say so in a way
    a reviewer will see, not slip it through here.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(SECRET_ENV_PREFIX)
    }
    if extra:
        for key, value in extra.items():
            if key.startswith(SECRET_ENV_PREFIX):
                raise ValueError(
                    f"refusing to pass {key} to a child process; MERIDIAN_* "
                    "variables stay in the sidecar (SEC-27)"
                )
            env[key] = value
    return env
