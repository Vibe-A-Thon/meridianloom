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

from .protocol import CORE_VERSION, PROTOCOL_VERSION

__all__ = ["PROTOCOL_VERSION", "CORE_VERSION"]
