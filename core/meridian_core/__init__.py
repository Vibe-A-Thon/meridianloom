"""Meridian Core sidecar package.

Spawned by the VS Code extension as ``python -m meridian_core`` and spoken to
over framed JSON-RPC 2.0 on stdio (FR-M3-01).

Wire protocol (both sides MUST agree):

* Framing is **newline-delimited JSON (NDJSON)**: every message is exactly one
  complete JSON-RPC 2.0 object serialised with :func:`json.dumps` (which never
  emits a raw newline inside strings) and terminated by a single ``\\n``.
* Encoding is UTF-8 on both stdin and stdout.
* stdout carries ONLY framed RPC (FR-M3-09). All logging goes to stderr and a
  rotating log file — see :mod:`meridian_core.log_setup`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _add_shared_types_to_path() -> None:
    """Make the generated message-bus types importable (FR-M32-09).

    The generator writes shared/py/bus_types.py; both layouts are supported:

    * development checkout: <repo>/shared/py next to <repo>/core;
    * packaged VSIX: <extensionPath>/sidecar/shared/py next to
      <extensionPath>/sidecar/meridian_core (the packaging script copies it).
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "shared" / "py"
        if candidate.is_dir():
            location = str(candidate)
            if location not in sys.path:
                sys.path.insert(0, location)
            return


_add_shared_types_to_path()

from .protocol import CORE_VERSION, PROTOCOL_VERSION  # noqa: E402

__all__ = ["PROTOCOL_VERSION", "CORE_VERSION"]
